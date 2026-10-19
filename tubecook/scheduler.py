"""Планировщик: слоты 00:00/06:00/12:00/18:00 Europe/Kyiv, DST, catch-up, TTL.

Политика пропущенных слотов (ноутбук спал/был выключен):
- после включения очередь восстанавливается (recovery в queue);
- НЕ выпускаем всю ночную очередь залпом: максимум catchup_max (по умолчанию 1)
  самых свежих готовых заданий, остальные сдвигаются на будущие слоты;
- перед публикацией проверяем свежесть новости (checked_at, TTL): протухшую
  в автопубликацию не отдаём, шлём одно уведомление админу;
- пустая очередь -> одно уведомление (не чаще раза в empty_notify_cooldown_h),
  никаких выдуманных новостей.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tubecook import db as dbm
from tubecook.config import Config
from tubecook.models import JobState, now_iso


def next_slot(cfg: Config, now: datetime | None = None) -> datetime:
    """Ближайший будущий слот (timezone-aware; DST учитывается zoneinfo)."""
    now = now or datetime.now(tz=cfg.tz)
    for hour in sorted(cfg.slots):
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate
    # все слоты сегодня прошли -> первый слот завтра
    return (now + timedelta(days=1)).replace(hour=sorted(cfg.slots)[0],
                                             minute=0, second=0, microsecond=0)


def slot_floor(now: datetime, slots: tuple) -> datetime:
    """Последний прошедший слот для момента now (для маркеров)."""
    best = None
    for hour in sorted(slots):
        cand = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if cand <= now and (best is None or cand > best):
            best = cand
    if best is not None:
        return best
    return (now - timedelta(days=1)).replace(hour=sorted(slots)[0], minute=0,
                                             second=0, microsecond=0)


@dataclass
class TickResult:
    publish_now: list = field(default_factory=list)     # [(job_id, slot_iso)]
    shifted: list = field(default_factory=list)          # [(job_id, new_slot)]
    stale: list = field(default_factory=list)            # job_id с истёкшим TTL
    notify_admin: list = field(default_factory=list)     # тексты уведомлений


class Scheduler:
    def __init__(self, conn, cfg: Config, queue):
        self.conn = conn
        self.cfg = cfg
        self.queue = queue

    # ------------------------------------------------------------------ tık

    def tick(self, now: datetime | None = None) -> TickResult:
        """Основной такт: вызывается демоном каждые ~30 c."""
        res = TickResult()
        now = now or datetime.now(tz=self.cfg.tz)
        if self.queue.is_paused():
            return res

        cur_slot = slot_floor(now, self.cfg.slots)
        last_marker = dbm.get_meta(self.conn, "last_slot", "")
        marker_dt = _parse_dt(last_marker)

        # публикабельные: отрендерены и одобрены (или автономный режим разрешён)
        ready = self._ready_jobs()

        if marker_dt is None or cur_slot > marker_dt:
            missed = self._missed_count(marker_dt, cur_slot)
            res = self._process_slot(cur_slot, ready, missed)
            dbm.set_meta(self.conn, "last_slot", cur_slot.isoformat(timespec="seconds"))
        else:
            # внутри слота: ручные задания с пройденным due публикуются сразу
            res.publish_now = self._due_manual(ready, now)
        return res

    # ------------------------------------------------------------------ слоты

    def _ready_jobs(self) -> list:
        """Готовые к публикации задания: rendered + одобрено/автономно."""
        rows = self.conn.execute(
            "SELECT job_id, payload, scheduled_slot, priority FROM jobs WHERE state=?"
            " ORDER BY created_at ASC", (JobState.RENDERED,)).fetchall()
        out = []
        for r in rows:
            payload = _loads(r["payload"])
            approved = self._is_approved(r["job_id"])
            if approved or (self.cfg.autonomous_mode and not self.cfg.require_approval):
                out.append({"job_id": r["job_id"], "payload": payload,
                            "slot": _parse_dt(r["scheduled_slot"]),
                            "priority": r["priority"]})
        return out

    def _is_approved(self, job_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM events WHERE job_id=? AND kind='approved' LIMIT 1",
            (job_id,)).fetchone()
        return row is not None

    def _process_slot(self, cur_slot: datetime, ready: list, missed: int) -> TickResult:
        res = TickResult()
        due_now = [j for j in ready if j["slot"] is None or j["slot"] <= cur_slot]

        # 1) свежесть (TTL) — протухшие не публикуем автоматически
        fresh = []
        for j in due_now:
            age_h = self._age_hours(j["payload"])
            if age_h is not None and age_h > self.cfg.news_ttl_h:
                res.stale.append(j["job_id"])
                dbm.event(self.conn, "news_stale", j["job_id"],
                          {"age_h": round(age_h, 1), "ttl_h": self.cfg.news_ttl_h})
                continue
            fresh.append(j)

        # 2) catch-up: не вываливаем ночную очередь залпом
        limit = self.cfg.catchup_max if missed > 1 else max(1, self.cfg.catchup_max)
        take, shift = fresh[:limit], fresh[limit:]
        res.publish_now = [(j["job_id"], cur_slot.isoformat(timespec="seconds"))
                           for j in take]
        for j in shift:
            new_slot = next_slot(self.cfg, cur_slot)
            res.shifted.append((j["job_id"], new_slot.isoformat(timespec="seconds")))
            self.queue._shift_slot(j["job_id"], new_slot)
            dbm.event(self.conn, "slot_shifted", j["job_id"],
                      {"new_slot": new_slot.isoformat(timespec="seconds")})
            # остальные готовые сдвигаются цепочкой на последующие слоты
            cur_slot = new_slot

        # 3) пустой слот -> одно уведомление (с дедупликацией уведомлений)
        if not fresh:
            res.notify_admin.append(
                f"слот {cur_slot.isoformat(timespec='seconds')}: нет свежих материалов. "
                "Автопубликация пропущена — выдуманных новостей не создаём.")
        if res.stale:
            res.notify_admin.append(
                "протухшие по TTL новости: " + ", ".join(res.stale) +
                " — нужно обновление задания (/allow-update).")
        return res

    def _due_manual(self, ready: list, now: datetime) -> list:
        """Ручные задания Сергея: публикуются сразу после одобрения."""
        out = []
        for j in ready:
            if j["priority"] == "manual" and (j["slot"] is None or j["slot"] <= now):
                out.append((j["job_id"], now.isoformat(timespec="seconds")))
        return out

    def _missed_count(self, marker_dt: datetime | None, cur_slot: datetime) -> int:
        if marker_dt is None:
            return 1
        n, cur = 0, marker_dt
        while cur < cur_slot:
            cur = next_slot(self.cfg, cur)
            n += 1
            if n > 8:
                break
        return max(n, 1)

    def _age_hours(self, payload: dict) -> float | None:
        checked = None
        for s in payload.get("sources", []):
            if s.get("checked_at"):
                checked = s["checked_at"]
                break
        if not checked:
            return None
        dt = _parse_dt(str(checked))
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.cfg.tz)   # даты без зоны — местное время Kyiv
        return (datetime.now(tz=self.cfg.tz) - dt).total_seconds() / 3600.0


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _loads(raw: str) -> dict:
    import json
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
