"""Сквозные сценарии бот-ядра: приём, дубли, конфликт, multipart, команды."""
from tubecook.bot.core import BotCore
from tubecook.models import JobState

from conftest import SAMPLE, SAMPLE_PART1, SAMPLE_PART2


def _say(core, sender, text):
    return core.handle_update({"sender_id": sender, "text": text})


def test_full_flow_accept_duplicate_conflict(core, q):
    # приём от авторизованного отправителя
    r = _say(core, 222, SAMPLE)
    assert "OK принято: test-job-001" in r[0]["text"]
    assert q.get("test-job-001") is not None

    # повтор того же задания — прежняя квитанция
    r = _say(core, 222, SAMPLE)
    assert r[0]["text"].startswith("DUPLICATE")

    # тот же ID, другое содержимое — конфликт без перезаписи
    conflict = SAMPLE.replace("Хук для теста протокола", "Совсем другой хук")
    r = _say(core, 222, conflict)
    assert r[0]["text"].startswith("CONFLICT")
    assert q.conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 1


def test_multipart_ack_only_after_all_parts(core, q):
    r1 = _say(core, 222, SAMPLE_PART1)
    assert "часть 1/2 принята" in r1[0]["text"]
    assert "Жду части: 2" in r1[0]["text"]
    # задания ещё нет — ACK не выдан
    assert q.get("test-part-001") is None

    r2 = _say(core, 222, SAMPLE_PART2)
    assert "OK принято: test-part-001" in r2[0]["text"]
    assert q.get("test-part-001")["state"] == JobState.QUEUED
    # inbox очищен после сборки
    assert q.conn.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"] == 0


def test_commands_flow(core, q):
    _say(core, 222, SAMPLE)
    assert "/status" in _say(core, 111, "/status")[0]["text"] or "статус" in \
        _say(core, 111, "/status")[0]["text"]

    # пауза
    r = _say(core, 111, "/pause тестовая")
    assert "публикации запрещены" in r[0]["text"]
    assert q.is_paused() is not None
    # резюм
    r = _say(core, 111, "/resume")
    assert q.is_paused() is None

    # /job
    r = _say(core, 111, "/job test-job-001")
    assert "queued" in r[0]["text"]

    # отмена с сохранением аудита
    _say(core, 111, "/cancel test-job-001")
    assert q.get("test-job-001")["state"] == JobState.CANCELLED
    assert q.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE job_id='test-job-001'").fetchone()["c"] >= 2


def test_demo_test_command_marks_not_news(core, q):
    r = _say(core, 111, "/test")
    assert "OK принято: demo-tubecook-v4" in r[0]["text"]
    import json
    payload = json.loads(q.get("demo-tubecook-v4")["payload"])
    assert payload["demo"] is True


def test_non_protocol_text_gets_hint(core):
    r = _say(core, 222, "просто текст без протокола")
    assert "#TUBECOOK_JOB" in r[0]["text"]


def test_admin_preview_before_render_is_honest(core, q):
    _say(core, 222, SAMPLE)
    r = _say(core, 111, "/preview test-job-001")
    assert "превью ещё не готово" in r[0]["text"]
