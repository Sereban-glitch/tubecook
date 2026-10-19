"""Тесты протокола задания: разбор, валидация, нормализация, хеши, multipart."""
import json

from tubecook.protocol import (content_hash, dedupe_key_for, extract_part_header,
                               normalize_url, parse_message, parse_text_message,
                               validate_payload)

from conftest import SAMPLE, SAMPLE_PART1, SAMPLE_PART2


def test_parse_sample_ok():
    r = parse_message(SAMPLE)
    assert r.ok, r.errors
    j = r.job
    assert j["job_id"] == "test-job-001"
    assert j["topic"] == "Тестовая тема конвейера"
    assert "42" in j["script"]
    assert j["sources"][0]["url"].startswith("https://example.com/post")
    assert j["sources"][0]["checked_at"] == "2026-10-18 10:00"
    assert j["facts"][0]["attribution"] == "Источник: example.com"
    assert j["visual_plan"] == ["stat: 42"]
    assert "тест" in j["tags"]
    assert j["requested_auto_publish"] is True  # данные, не команда
    assert j["language"] == "ru"


def test_parse_missing_script():
    text = SAMPLE.replace("SCRIPT:", "SCRIPTX:")  # выпадает ключевое поле
    r = parse_message(text)
    assert not r.ok
    assert any("SCRIPT" in e for e in r.errors)


def test_parse_bad_id():
    text = SAMPLE.replace("test-job-001", "BAD ID!!")
    r = parse_message(text)
    assert not r.ok and any("ID" in e for e in r.errors)


def test_parse_no_sources_fails():
    text = SAMPLE.replace("- https://example.com/post?utm_source=x | 2026-10-18 | 2026-10-18 10:00", "")
    r = parse_message(text)
    assert not r.ok
    assert any("SOURCES" in e or "checked_at" in e for e in r.errors)


def test_parse_facts_without_attribution_fails():
    text = SAMPLE.replace("- Факт один подтверждён | Источник: example.com | https://example.com/post",
                          "- Факт один подтверждён")
    r = parse_message(text)
    assert not r.ok and any("атрибуции" in e for e in r.errors)


def test_json_fenced_parse():
    payload = {
        "job_id": "json-job-1", "topic": "Тема", "hook": "Хук",
        "script": "Достаточно длинный сценарий для проверки JSON-формата, чтобы пройти"
                  " валидацию по длине и содержанию без каких-либо проблем."
                  " Здесь ровно столько текста, чтобы выйти за минимум в сто двадцать символов.",
        "sources": [{"url": "https://a.example/x", "published": "2026-10-01",
                     "checked_at": "2026-10-02 10:00"}],
        "facts": [{"text": "Факт", "attribution": "src"}],
        "language": "ru",
    }
    text = "#TUBECOOK_JOB v4\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    r = parse_message(text)
    assert r.ok, r.errors
    assert r.job["job_id"] == "json-job-1"


def test_normalize_url_strips_trackers():
    u = "https://Example.com/post/?utm_source=tg&id=5"
    assert normalize_url(u) == "https://example.com/post?id=5"


def test_content_hash_stable_and_sensitive():
    r = parse_message(SAMPLE)
    h1 = content_hash(r.job)
    h2 = content_hash(parse_message(SAMPLE).job)
    assert h1 == h2
    changed = dict(r.job)
    changed["script"] = r.job["script"] + " ещё фраза."
    assert content_hash(changed) != h1


def test_dedupe_key_by_url():
    r = parse_message(SAMPLE)
    assert dedupe_key_for(r.job).startswith("url:")
    p2 = dict(r.job)
    p2["sources"] = []
    assert dedupe_key_for(p2).startswith("content:")


def test_multipart_header_extraction():
    got = extract_part_header(SAMPLE_PART1)
    assert got is not None and got[0] == 1 and got[1] == 2


def test_header_line_inside_multipart_is_ignored():
    assembled = SAMPLE_PART1 + "\n" + SAMPLE_PART2
    r = parse_message(assembled)
    assert r.ok, r.errors
    assert r.job["job_id"] == "test-part-001"
    assert "многочастного" in r.job["script"]


def test_validate_payload_direct():
    errs = validate_payload({})
    assert len(errs) >= 6   # id/topic/hook/script/sources/facts
