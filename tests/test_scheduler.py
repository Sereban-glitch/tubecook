"""Планировщик: слоты Europe/Kyiv, DST, catch-up, TTL, пустая очередь, пауза."""
from datetime import datetime, timedelta

from tubecook import db as dbm
from tubecook.models import JobState
from tubecook.scheduler import Scheduler, next_slot, slot_floor
from tubecook.protocol import parse_message

from conftest import SAMPLE


def _mk_job(q, jid, checked_at="2026-10-18 09:00", slot=None, role="sender"):
    from datetime import datetime, timedelta
    text = SAMPLE.replace("test-job-001", jid) \
                 .replace("https://example.com/post?utm_source=x",
                          f"https://example.com/{jid}") \
                 .replace("2026-10-18 10:00", checked_at)
    parsed = parse_message(text)
    q.submit(parsed.job, sender_id=222, role=role)
    q.complete_stage(jid, JobState.RENDERED, "test")
    q.approve(jid, admin_id=111)
    # слот публикации: в прошлом относительно тестового момента 2026-10-18
    past = slot or (datetime(2026, 10, 18, 0, 0, tzinfo=q.cfg.tz) - timedelta(hours=12))
    q._shift_slot(jid, past)
    return jid


# ------------------------------------------------------------------ слоты/DST

def test_next_slot_basic(cfg):
    now = datetime(2026, 10, 18, 5, 0, tzinfo=cfg.tz)
    assert next_slot(cfg, now).hour == 6
    late = datetime(2026, 10, 18, 23, 30, tzinfo=cfg.tz)
    ns = next_slot(cfg, late)
    assert ns.hour == 0 and ns.day == 19


def test_slots_exist_exactly_four_on_dst_spring_day(cfg):
    """29.03.2026 (EET->EEST): все 4 слота существуют и различны."""
    from datetime import timezone
    cur = datetime(2026, 3, 28, 23, 30, tzinfo=cfg.tz)
    seen = []
    for _ in range(4):
        ns = next_slot(cfg, cur)
        seen.append(ns)
        cur = ns + timedelta(minutes=1)
    assert len({s.isoformat() for s in seen}) == 4
    # NB: вычитание дат с одинаковым tzinfo игнорирует DST (CPython),
    # поэтому абсолютные интервалы считаем через UTC
    utc = [s.astimezone(timezone.utc) for s in seen]
    delta = (utc[1] - utc[0]).total_seconds() / 3600
    assert 4.9 < delta < 5.1      # 00:00 EET -> 06:00 EEST = 5 реальных часов
    delta2 = (utc[2] - utc[1]).total_seconds() / 3600
    assert abs(delta2 - 6.0) < 0.1


def test_slots_exist_exactly_four_on_dst_fall_day(cfg):
    """25.10.2026 (EEST->EET): 4 слота, между 00 и 06 — 7 часов."""
    from datetime import timezone
    cur = datetime(2026, 10, 24, 23, 30, tzinfo=cfg.tz)
    seen = []
    for _ in range(4):
        ns = next_slot(cfg, cur)
        seen.append(ns)
        cur = ns + timedelta(minutes=1)
    assert len({s.isoformat() for s in seen}) == 4
    utc = [s.astimezone(timezone.utc) for s in seen]
    delta = (utc[1] - utc[0]).total_seconds() / 3600
    assert 6.9 < delta < 7.1      # 00:00 EEST -> 06:00 EET = 7 реальных часов


def test_slot_floor_dst_safe(cfg):
    now = datetime(2026, 10, 25, 4, 30, tzinfo=cfg.tz)
    assert slot_floor(now, cfg.slots).hour == 0


# ------------------------------------------------------------------ catch-up

def test_catchup_max_one_after_missed_slots(q, cfg):
    """Ноутбук спал: 2 слота пропущены — публикуем максимум 1, остальные сдвигаются."""
    jids = [_mk_job(q, f"sleep-{i}") for i in range(3)]
    now = datetime(2026, 10, 18, 12, 5, tzinfo=cfg.tz)
    # маркер старый: последняя обработка была в 00:00 (2 слота назад)
    dbm.set_meta(q.conn, "last_slot",
                 datetime(2026, 10, 18, 0, 0, tzinfo=cfg.tz).isoformat())
    sched = Scheduler(q.conn, cfg, q)
    tick = sched.tick(now=now)
    assert len(tick.publish_now) == 1
    assert len(tick.shifted) == 2
    # сдвинутые получили будущий слот
    for jid, new_slot in tick.shifted:
        assert q.get(jid)["scheduled_slot"] == new_slot


def test_stale_news_not_published_auto(q, cfg):
    """TTL: протухшая новость не выходит в автопубликацию, админ получает уведомление."""
    jid = _mk_job(q, "old-1", checked_at="2026-10-01 09:00")  # давно проверена
    now = datetime(2026, 10, 18, 12, 5, tzinfo=cfg.tz)
    dbm.set_meta(q.conn, "last_slot",
                 datetime(2026, 10, 18, 6, 0, tzinfo=cfg.tz).isoformat())
    sched = Scheduler(q.conn, cfg, q)
    tick = sched.tick(now=now)
    assert all(jid != "old-1" for jid, _ in tick.publish_now)
    assert "old-1" in tick.stale
    assert any("протухшие" in t for t in tick.notify_admin)


def test_empty_queue_single_notification_no_invented_news(q, cfg):
    now = datetime(2026, 10, 18, 12, 5, tzinfo=cfg.tz)
    dbm.set_meta(q.conn, "last_slot",
                 datetime(2026, 10, 18, 6, 0, tzinfo=cfg.tz).isoformat())
    sched = Scheduler(q.conn, cfg, q)
    tick = sched.tick(now=now)
    assert tick.publish_now == []
    assert any("нет свежих материалов" in t for t in tick.notify_admin)


def test_paused_scheduler_no_actions(q, cfg):
    _mk_job(q, "paused-1")
    q.pause(by=111)
    now = datetime(2026, 10, 18, 12, 5, tzinfo=cfg.tz)
    dbm.set_meta(q.conn, "last_slot",
                 datetime(2026, 10, 18, 6, 0, tzinfo=cfg.tz).isoformat())
    sched = Scheduler(q.conn, cfg, q)
    tick = sched.tick(now=now)
    assert tick.publish_now == [] and tick.shifted == []


def test_unapproved_not_published(q, cfg):
    """HITL: без /approve автопубликация не стартует (первый выпуск видит владелец)."""
    parsed = parse_message(SAMPLE)
    q.submit(parsed.job, sender_id=222, role="sender")
    q.complete_stage("test-job-001", JobState.RENDERED, "t")
    now = datetime(2026, 10, 18, 12, 5, tzinfo=cfg.tz)
    dbm.set_meta(q.conn, "last_slot",
                 datetime(2026, 10, 18, 6, 0, tzinfo=cfg.tz).isoformat())
    sched = Scheduler(q.conn, cfg, q)
    tick = sched.tick(now=now)
    assert tick.publish_now == []
