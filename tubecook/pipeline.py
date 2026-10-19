"""Пайплайн: claim -> рендер (cancel-aware) -> превью -> одобрение -> публикация.

Гарантии:
- рендер доезжает до конца даже при паузе (пауза блокирует только публикацию);
- отмена между стадиями проверяется, аудит не стирается;
- публикация идёт per-target: упавшая площадка повторяется, успешная — нет;
- dry-run никогда не называется публикацией (событие published_dry_run).
"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

from tubecook.media import deliver, render
from tubecook.models import JobState
from tubecook.scheduler import next_slot


class Pipeline:
    def __init__(self, cfg, queue, bot=None, publishers=None):
        self.cfg = cfg
        self.queue = queue
        self.bot = bot                # BotCore (уведомления) или None
        self.publishers = publishers or {}

    # ------------------------------------------------------------------ рендер

    def process_next(self, owner: str = "worker") -> str | None:
        row = self.queue.claim(owner)
        if row is None:
            return None
        jid = row["job_id"]
        payload = json.loads(row["payload"])
        try:
            self.render_job(jid, payload, owner)
        except Exception as e:
            receipt = self.queue.fail(jid, f"{type(e).__name__}: {e}", owner)
            self._notify(f"СБОЙ РЕНДЕРА {jid}: {receipt.detail}")
        return jid

    def render_job(self, jid: str, payload: dict, owner: str = "worker") -> dict:
        def cancelled() -> bool:
            row = self.queue.get(jid)
            return row is not None and row["state"] == JobState.CANCELLED

        work = Path(self.cfg.jobs_dir) / jid
        # артефакты прошлой попытки — продолжаем с места (resume по файлам)
        self.queue.complete_stage(jid, JobState.RENDERING, owner)
        res = render.render_episode(payload, self.cfg, work,
                                     profile=self.cfg.render.profile)
        if cancelled():
            self._notify(f"{jid}: отменён во время рендера (аудит сохранён)")
            return res

        tg = deliver.encode_telegram(res["master"], work / "telegram.mp4", self.cfg)
        deliver.extract_thumbnail(res["master"], work / "thumb.jpg")
        self.queue.complete_stage(jid, JobState.RENDERED, owner)

        # превью лично Сергею, отдельно от публикации (ТЗ)
        if self.cfg.require_approval:
            self.queue.set_awaiting_approval(jid)
            self._notify(f"РЕНДЕР ГОТОВ: {jid} ({res['report']['total_s']} c, "
                         f"master {res['report']['master_mb']} МБ). "
                         "Превью прилагаю; публикация — после /approve.",
                         file=str(tg["path"]))
        else:
            self._notify(f"РЕНДЕР ГОТОВ: {jid}; выйдет в плановый слот "
                         "(HITL выключен).")
        return res

    # ------------------------------------------------------------------ публикация

    def publish_job(self, jid: str, owner: str = "publisher") -> dict:
        paused = self.queue.is_paused()
        if paused:
            self._notify(f"ПАУЗА: публикация {jid} отложена "
                         f"(причина: {paused.get('reason') or '-'})")
            return {"skipped": "paused"}

        row = self.queue.get(jid)
        if row is None:
            return {"error": "задание не найдено"}
        payload = json.loads(row["payload"])
        self.queue.mark_publishing(jid, owner)

        work = Path(self.cfg.jobs_dir) / jid
        artifacts = {"master": str(work / "master.mp4"),
                     "telegram_video": str(work / "telegram.mp4")}

        for name, pub in self.publishers.items():
            cur = self.queue.target_states(jid).get(name, {})
            state = cur.get("state")
            if state == "sent":
                continue                      # частичный успех: не дублируем
            if state == "uncertain":
                res = pub.verify(jid, cur.get("result_ref") or "")
                if res.state == "sent":
                    self.queue.set_target(jid, name, "sent", result_ref=res.ref)
                    continue
                if res.state == "failed":
                    self._notify(f"{jid}/{name}: сверка показала, что загрузки "
                                 "не было — будет повтор при следующем заходе")
            res = pub.publish(payload, artifacts)
            self.queue.set_target(jid, name, res.state,
                                  result_ref=res.ref, error=res.error)
            if res.state == "uncertain":
                self._notify(f"UNCERTAIN {jid}/{name}: {res.error}. "
                             "Возможно, уже опубликовано — сверьте (/check). "
                             "Слепой повтор не делаем.")
            elif res.state == "failed":
                self._notify(f"СБОЙ {jid}/{name}: {res.error[:300]}")

        states = {n: self.queue.target_states(jid).get(n, {}).get("state")
                  for n in self.publishers}
        ok = all(s in ("sent", "dry_run") for s in states.values() if s)
        if ok:
            dry = any(s == "dry_run" for s in states.values())
            self.queue.mark_published(jid)
            if dry:
                # честно: это НЕ публикация в канал, это доставка в outbox
                self._notify(f"{jid}: DRY-RUN завершён (реальные API не "
                             "вызывались; пакеты в data/outbox). В очередь "
                             "возвращать не нужно.")
                self._event(jid, "published_dry_run", {"targets": states})
            else:
                self._notify(f"{jid}: опубликовано: {json.dumps(states)}")
            return {"published": True, "targets": states}
        # что-то упало: возврат в RENDERED, слот сдвигаем на сутки, повтор
        # только на слоте или после нового /approve — не спамим API
        slot = next_slot(self.cfg, datetime_now() + timedelta(hours=23))
        self.queue._shift_slot(jid, slot)
        self.queue.complete_stage(jid, JobState.RENDERED, owner)
        self._event(jid, "publish_partial", {"targets": states})
        return {"published": False, "targets": states}

    # ------------------------------------------------------------------ утилиты

    def _notify(self, text: str, file: str | None = None) -> None:
        if self.bot is not None:
            self.bot.notify_admin(text, file=file)

    def _event(self, jid: str, kind: str, data: dict) -> None:
        from tubecook import db as dbm
        dbm.event(self.queue.conn, kind, jid, data)


def datetime_now():
    from datetime import datetime
    return datetime.now()
