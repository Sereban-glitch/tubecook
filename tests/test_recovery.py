"""Восстановление после падения/sleep: lease, retry, uncertain-цели."""
import time

from tubecook.models import JobState, TargetState

from conftest import SAMPLE
from tubecook.protocol import parse_message


def _seed(q):
    parsed = parse_message(SAMPLE)
    q.submit(parsed.job, sender_id=222, role="sender")
    return "test-job-001"


def test_stale_rendering_requeued_with_attempt(q):
    jid = _seed(q)
    q.claim(owner="w1")
    # процесс «умер»: lease в прошлом
    q.conn.execute("UPDATE jobs SET lease_until=? WHERE job_id=?",
                   (time.time() - 100, jid))
    touched = q.recovery(boot=True)
    assert jid in touched
    row = q.get(jid)
    assert row["state"] == JobState.QUEUED
    assert row["attempts"] == 1
    # due_at в будущем из-за backoff: залпом не перезапускаем
    assert row["due_at"] > time.time()


def test_recovery_final_fail_after_max_attempts(q, cfg):
    jid = _seed(q)
    for _ in range(cfg.max_attempts):
        q.claim(owner="w")
        q.fail(jid, "падение", "w")
        q.conn.execute("UPDATE jobs SET lease_until=? WHERE job_id=?",
                       (time.time() - 100, jid))
        q.recovery()
    assert q.get(jid)["state"] == JobState.FAILED


def test_uncertain_target_never_blindly_resent(q):
    jid = _seed(q)
    q.complete_stage(jid, JobState.RENDERED, "w")
    q.set_target(jid, "telegram", TargetState.UNCERTAIN, result_ref="777")
    q.recovery(boot=True)
    states = q.target_states(jid)
    assert states["telegram"]["state"] == TargetState.UNCERTAIN
    # повторная recovery не меняет uncertain — решение за verify/человеком
    q.recovery()
    assert q.target_states(jid)["telegram"]["state"] == TargetState.UNCERTAIN


def test_fresh_lease_not_requeued(q):
    jid = _seed(q)
    q.claim(owner="w1")
    touched = q.recovery()
    assert jid not in touched      # активный lease не отбирается
    assert q.get(jid)["state"] == JobState.RENDERING
