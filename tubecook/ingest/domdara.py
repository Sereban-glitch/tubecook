"""Модуль сбора статей с сайта кооператива «Домдара» (http://domdara.org/feed/).

Реализует:
1. Запрос RSS (HTTP, WordPress 2.0).
2. Защиту от выкачивания многолетнего архива при первом запуске (Initial Boundary).
3. Восстановление пропущенных статей после сна ноутбука с хронологической сортировкой (oldest -> newest).
4. Дедупликацию по GUID/URL.
5. Интеграцию с ИИ-анализом и постановку в очередь Tubecook (Priority.DOMDARA).
"""
from __future__ import annotations

import email.utils
import hashlib
import logging
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any

from tubecook import db as dbm
from tubecook.ai.analyzer import ScriptAnalyzer
from tubecook.ai.client import AIClient, AIProxyError
from tubecook.config import Config
from tubecook.models import Priority, now_iso
from tubecook.queue import Queue

logger = logging.getLogger(__name__)


def parse_rss_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Парсит XML-ленту RSS 2.0 в список словарей."""
    try:
        root = ET.fromstring(xml_bytes)
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise ValueError(f"Ошибка разбора RSS XML: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        raise ValueError("В RSS XML отсутствует элемент <channel>")

    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        pub_str = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()

        content = ""
        for child in item:
            if child.tag.endswith("encoded"):
                content = (child.text or "").strip()
                break

        pub_dt: datetime | None = None
        if pub_str:
            try:
                pub_dt = email.utils.parsedate_to_datetime(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)
        else:
            pub_dt = datetime.now(timezone.utc)

        item_id = guid or link or title
        if not item_id or not link:
            continue

        items.append({
            "id": item_id,
            "guid": guid or item_id,
            "title": title,
            "link": link,
            "published_str": pub_str,
            "pub_dt": pub_dt,
            "description": desc,
            "content": content,
        })

    return items


def fetch_url(url: str, user_agent: str = "Mozilla/5.0 Codex Bridge", timeout: float = 20.0) -> bytes:
    """Выполняет HTTP-запрос (обходит невалидный SSL, если передан https)."""
    # Если передан https на domdara, принудительно переключаем на http
    if "domdara.org" in url and url.startswith("https://"):
        url = url.replace("https://", "http://", 1)

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class DomdaraIngest:
    def __init__(self, cfg: Config, queue: Queue, analyzer: ScriptAnalyzer | None = None):
        self.cfg = cfg
        self.queue = queue
        self.conn = queue.conn
        if analyzer is None:
            ai_client = AIClient(endpoint=cfg.ai_proxy_url, api_key=cfg.ai_proxy_key, model=cfg.ai_model)
            analyzer = ScriptAnalyzer(client=ai_client)
        self.analyzer = analyzer

    def poll_feed(self, max_pages: int = 5) -> list[dict[str, Any]]:
        """Запрашивает RSS-ленту, следуя по страницам при необходимости."""
        all_items: list[dict[str, Any]] = []
        base_url = self.cfg.domdara_feed_url

        for page in range(1, max_pages + 1):
            url = base_url if page == 1 else f"{base_url.rstrip('/')}/?paged={page}"
            try:
                raw_xml = fetch_url(url, user_agent=self.cfg.domdara_user_agent)
                items = parse_rss_xml(raw_xml)
            except Exception as exc:
                logger.warning("Ошибка загрузки страницы %d ленты Domdara (%s): %s", page, url, exc)
                break

            if not items:
                break

            all_items.extend(items)

            # Если на странице меньше 10 записей, пагинация закончилась
            if len(items) < 10:
                break

        return all_items

    def get_unseen_items(self, items: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
        """Фильтрует новые статьи с учётом границы первого запуска и хронологии."""
        now = now or datetime.now(timezone.utc)
        last_guid = dbm.get_meta(self.conn, "domdara_last_seen_guid", "")

        # ХОЛОДНЫЙ СТАРТ (база пуста, курсор не установлен)
        if not last_guid:
            logger.info("Холодный старт Domdara: установка начальной границы (режим %s)", self.cfg.domdara_seed_mode)
            if self.cfg.domdara_seed_mode == "latest_only":
                if items:
                    latest = max(items, key=lambda x: x["pub_dt"])
                    dbm.set_meta(self.conn, "domdara_last_seen_guid", latest["guid"])
                    dbm.set_meta(self.conn, "domdara_last_pub_date", latest["pub_dt"].isoformat())
                return []

            # Режим lookback: берем только статьи за последние N дней
            cutoff = now - timedelta(days=self.cfg.domdara_initial_lookback_days)
            candidates = [it for it in items if it["pub_dt"] >= cutoff]
            # Сортировка СТРОГО от старых к новым
            candidates.sort(key=lambda x: x["pub_dt"])
            return candidates

        # РЕГУЛЯРНЫЙ РЕЖИМ (catch-up после сна)
        # Находим статьи, которые мы ещё не видели
        # 1. Проверяем наличие dedupe_key в таблице jobs
        unseen = []
        for it in items:
            dkey = f"domdara:guid:{it['guid']}"
            existing = self.conn.execute("SELECT 1 FROM jobs WHERE dedupe_key=?", (dkey,)).fetchone()
            if existing is None and it["guid"] != last_guid:
                unseen.append(it)

        # СОРТИРОВКА: хронологически от старых к новым (oldest -> newest)
        unseen.sort(key=lambda x: x["pub_dt"])
        return unseen

    def ingest_once(self, dry_run: bool = False, limit: int = 10) -> list[str]:
        """Один такт сбора: опрос ленты, ИИ-разбор и постановка в очередь."""
        if not self.cfg.domdara_enabled:
            return []

        feed_items = self.poll_feed(max_pages=3)
        if not feed_items:
            return []

        pending = self.get_unseen_items(feed_items)
        if limit:
            pending = pending[:limit]

        enqueued_ids: list[str] = []

        for item in pending:
            guid = item["guid"]
            link = item["link"]
            title = item["title"]
            pub_iso = item["pub_dt"].isoformat()

            logger.info("Обработка статьи Домдары: %s (%s)", title, link)

            # Загружаем полный HTML статьи
            try:
                html_bytes = fetch_url(link, user_agent=self.cfg.domdara_user_agent)
                html_text = html_bytes.decode("utf-8", errors="ignore")
            except Exception as exc:
                logger.error("Не удалось загрузить HTML статьи %s: %s", link, exc)
                continue

            # ИИ-разбор статьи
            try:
                analyzed = self.analyzer.analyze_article(
                    title=title,
                    link=link,
                    guid=guid,
                    published=pub_iso,
                    html_content=html_text,
                )
            except AIProxyError as exc:
                logger.warning("ИИ-прокси недоступен для статьи %s: %s (пропуск до следующего такта)", guid, exc)
                # По ТЗ: не публиковать сырой материал, не терять новость
                continue
            except Exception as exc:
                logger.error("Неожиданная ошибка анализа статьи %s: %s", guid, exc)
                continue

            # Формируем ID задания
            clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", guid.replace("http://domdara.org/?p=", "p"))
            job_id = f"domdara-{clean_id}-{item['pub_dt'].strftime('%Y%m%d')}"

            payload = {
                "job_id": job_id,
                "topic": analyzed["topic"],
                "hook": analyzed["hook"],
                "script": analyzed["script"],
                "visual_plan": analyzed.get("visual_plan", []),
                "facts": analyzed.get("facts", []),
                "sources": analyzed.get("sources", []),
                "tags": analyzed.get("tags", []),
                "language": "ru",
                "requested_mode": "approval",   # требует проверки Сергеем
                "requested_priority": "domdara",
                "dedupe_key": f"domdara:guid:{guid}",
                "meta": analyzed.get("meta", {}),
            }

            if dry_run:
                logger.info("[DRY-RUN] Подготовлено задание: %s | %s", job_id, payload["topic"])
                enqueued_ids.append(job_id)
                continue

            # Постановка в очередь
            receipt = self.queue.submit(
                payload=payload,
                sender_id=-100,  # системный отправитель Domdara
                role="domdara",
            )
            if receipt.status in ("accepted", "duplicate"):
                enqueued_ids.append(job_id)
                # Обновляем курсор в базе
                dbm.set_meta(self.conn, "domdara_last_seen_guid", guid)
                dbm.set_meta(self.conn, "domdara_last_pub_date", pub_iso)
                logger.info("Задание %s успешно поставлено в очередь (%s)", job_id, receipt.status)

        return enqueued_ids
