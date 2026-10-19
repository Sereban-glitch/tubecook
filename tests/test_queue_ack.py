"""Очередь: атомарный ACK, идемпотентность, дедуп, конфликты, allow-update."""
import json

from tubecook.models import JobState
from tubecook.protocol import parse_message

from conftest import SAMPLE


def _submit(q, text, sender=222, role="sender", **kw):
    parsed = parse_message(text)
    assert parsed.ok, parsed.errors
    return q.submit(parsed.job, sender_id=sender, role=role, **kw)


def test_ack_after_atomic_save(q):
    r = _submit(q, SAMPLE)
    assert r.status == "accepted"
    assert r.state == JobState.QUEUED
    assert r.position >= 1
    assert r.planned_slot  # ISO со слотом Europe/Kyiv
    row = q.get("test-job-001")
    assert row is not None and row["state"] == JobState.QUEUED
    # ACK только после сохранения: событие accepted уже в аудите
    ev = q.conn.execute("SELECT COUNT(*) c FROM events WHERE kind='accepted'").fetchone()
    assert ev["c"] == 1


def test_duplicate_same_id_same_content_returns_old_receipt(q):
    r1 = _submit(q, SAMPLE)
    r2 = _submit(q, SAMPLE)
    assert r2.status == "duplicate"
    assert r2.job_id == r1.job_id
    assert r2.content_hash == r1.content_hash
    # второго задания в БД не появилось
    n = q.conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    assert n == 1


def test_conflicting_id_different_content(q):
    _submit(q, SAMPLE)
    other = SAMPLE.replace("Тестовая тема конвейера", "Другая тема вовсе иная")
    other = other.replace("test-job-001", "same-id-diff")
    # под тем же ID, но с другим содержимым:
    conflict = SAMPLE.replace("Тестовая тема конвейера", "Другая тема вовсе иная")
    r = _submit(q, conflict)
    assert r.status == "conflict"
    assert "новый job_id" in r.render_text()
    # оригинал не перезаписан
    row = q.get("test-job-001")
    assert json.loads(row["payload"])["topic"] == "Тестовая тема конвейера"


def test_dedupe_by_canonical_url_different_id(q):
    _submit(q, SAMPLE)
    dup = SAMPLE.replace("test-job-001", "test-job-002")\
                .replace("utm_source=x", "utm_campaign=y")   # трекер не меняет канонический URL
    r = _submit(q, dup)
    assert r.status == "duplicate"
    assert "test-job-001" in r.render_text()


def test_allow_update_permits_resubmit(q):
    _submit(q, SAMPLE)
    r = q.allow_update(111, "test-job-001")
    assert r.status == "accepted"
    dup = SAMPLE.replace("test-job-001", "test-job-003")
    r2 = _submit(q, dup)
    assert r2.status == "accepted"
    # старое отменено, аудит жив
    assert q.get("test-job-001")["state"] == JobState.CANCELLED
    ev = q.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE job_id='test-job-001'").fetchone()["c"]
    assert ev >= 2


def test_claim_manual_priority_first(q):
    auto = SAMPLE.replace("test-job-001", "auto-1") \
                 .replace("example.com/post", "example.com/auto")
    manual = SAMPLE.replace("test-job-001", "manual-1") \
                   .replace("example.com/post", "example.com/manual")
    _submit(q, auto, role="sender")
    _submit(q, manual, role="admin")
    row = q.claim(owner="w1")
    assert row["job_id"] == "manual-1"


def test_claim_respects_future_due(q, monkeypatch):
    _submit(q, SAMPLE)
    q.fail("test-job-001", "тестовый сбой", "w1")     # retry: due_at в будущем
    assert q.claim(owner="w2") is None


def test_retry_backoff_then_failed(q):
    _submit(q, SAMPLE)
    for i in range(q.cfg.max_attempts):
        q.claim(owner=f"w{i}")
        q.fail("test-job-001", f"сбой {i}", f"w{i}")
    assert q.get("test-job-001")["state"] == JobState.FAILED


def test_cancel_keeps_audit(q):
    _submit(q, SAMPLE)
    q.cancel("test-job-001", by=111, reason="тест")
    assert q.get("test-job-001")["state"] == JobState.CANCELLED
    ev = q.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE job_id='test-job-001'"
        " AND kind='cancelled'").fetchone()["c"]
    assert ev == 1
