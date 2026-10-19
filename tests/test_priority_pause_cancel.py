"""Пауза/отмена/приоритет на уровне пайплайна и ядра бота."""
import json

from tubecook.models import JobState
from tubecook.pipeline import Pipeline
from tubecook.protocol import parse_message

from conftest import SAMPLE


def _seed(q, n=1):
    ids = []
    for i in range(n):
        text = SAMPLE.replace("test-job-001", f"job-{i:03d}") \
                     .replace("example.com/post", f"example.com/job-{i:03d}")
        parsed = parse_message(text)
        q.submit(parsed.job, sender_id=222, role="sender")
        ids.append(f"job-{i:03d}")
    return ids


def test_pause_blocks_publishing_but_not_render(q, cfg):
    ids = _seed(q, 1)
    msg = q.pause(by=111, reason="ночная пауза")
    assert "публикации запрещены" in msg
    assert "рендер" in msg and "rendered" in msg   # объясняет судьбу начатого

    class _Pub:
        name = "telegram"

        def publish(self, job, artifacts):
            raise AssertionError("пауза должна запрещать публикацию")

    pipe = Pipeline(cfg, q, publishers={"telegram": _Pub()})
    res = pipe.publish_job(ids[0])
    assert res.get("skipped") == "paused"


def test_cancel_during_pipeline_keeps_audit(q, cfg):
    ids = _seed(q, 1)
    q.cancel(ids[0], by=111, reason="отмена теста")
    pipe = Pipeline(cfg, q, publishers={})
    # рендер не стартует по отменённому: claim берёт только queued
    assert q.claim(owner="w") is None
    ev = q.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE job_id=? AND kind='cancelled'",
        (ids[0],)).fetchone()["c"]
    assert ev == 1


def test_partial_publish_retries_only_failed_target(q, cfg):
    ids = _seed(q, 1)
    jid = ids[0]
    q.complete_stage(jid, JobState.RENDERED, "test")

    class OkPub:
        name = "telegram"
        calls = 0

        def publish(self, job, artifacts):
            OkPub.calls += 1
            from tubecook.publish.base import TargetResult
            from tubecook.models import TargetState
            return TargetResult("telegram", TargetState.SENT, ref="42")

    class FailPub:
        name = "youtube"
        calls = 0

        def publish(self, job, artifacts):
            FailPub.calls += 1
            from tubecook.publish.base import TargetResult
            from tubecook.models import TargetState
            return TargetResult("youtube", TargetState.FAILED, error="тестовый сбой")

    pipe = Pipeline(cfg, q, publishers={"telegram": OkPub(), "youtube": FailPub()})
    res = pipe.publish_job(jid)
    assert res["published"] is False
    assert res["targets"]["telegram"] == "sent"
    assert res["targets"]["youtube"] == "failed"
    # только упавшая площадка повторяется при следующем заходе:
    res2 = pipe.publish_job(jid)
    assert OkPub.calls == 1 and FailPub.calls == 2
    assert res2["published"] is False


def test_dry_run_targets_are_not_called_success(q, cfg):
    ids = _seed(q, 1)
    jid = ids[0]
    q.complete_stage(jid, JobState.RENDERED, "test")

    from tubecook.publish.base import TargetResult
    from tubecook.models import TargetState

    class DryPub:
        name = "telegram"

        def publish(self, job, artifacts):
            return TargetResult("telegram", TargetState.DRY_RUN, ref="outbox/x")

    pipe = Pipeline(cfg, q, publishers={"telegram": DryPub()})
    res = pipe.publish_job(jid)
    assert res["published"] is True
    # честность: событие published_dry_run, НЕ «публикация в канал»
    ev = q.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE job_id=? AND kind='published_dry_run'",
        (jid,)).fetchone()["c"]
    assert ev == 1


def test_manual_job_publishes_out_of_turn(q, cfg, monkeypatch):
    """Ручная тема Сергея: после одобрения уходит вне общей очереди."""
    ids = _seed(q, 2)
    manual = SAMPLE.replace("test-job-001", "manual-1") \
                   .replace("example.com/post", "example.com/manual-1")
    parsed = parse_message(manual)
    q.submit(parsed.job, sender_id=111, role="admin")
    q.complete_stage("manual-1", JobState.RENDERED, "test")
    q.approve("manual-1", admin_id=111)
    from datetime import datetime, timedelta
    q._shift_slot("manual-1", datetime.now(tz=cfg.tz) - timedelta(hours=1))

    from tubecook.scheduler import Scheduler, slot_floor
    sched = Scheduler(q.conn, cfg, q)
    now = datetime.now(tz=cfg.tz)
    from tubecook import db as dbm
    dbm.set_meta(q.conn, "last_slot", slot_floor(now, cfg.slots).isoformat())
    tick = sched.tick(now=now)
    ids_in = [jid for jid, _ in tick.publish_now]
    assert "manual-1" in ids_in
    assert "job-000" not in ids_in   # авто-задания ждут одобрения/своего слота
