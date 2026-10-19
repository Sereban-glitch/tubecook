"""Публикаторы: dry-run без сети, uncertain при таймауте, честность формулировок."""
import json

import pytest

from tubecook.models import TargetState
from tubecook.publish.base import TargetResult
from tubecook.publish.telegram_pub import TelegramPublisher
from tubecook.publish.youtube_pub import YouTubePublisher

from conftest import SAMPLE
from tubecook.protocol import parse_message

JOB = {"job_id": "pub-1", "topic": "Тема", "hook": "Хук", "script": "Сценарий.",
       "sources": [{"url": "https://a.example/x", "checked_at": "2026-10-18 10:00"}],
       "facts": [{"text": "ф", "attribution": "а"}], "tags": ["т"], "meta": {}}
ARTS = {"master": "/nonexistent/master.mp4", "telegram_video": "/nonexistent/tg.mp4"}


def test_telegram_dry_run_writes_outbox_no_network(cfg, monkeypatch):
    cfg.dry_run_publish = True

    def _no_network(*a, **kw):
        raise AssertionError("dry-run не должен ходить в сеть")

    monkeypatch.setattr("requests.post", _no_network)
    monkeypatch.setattr("requests.get", _no_network)
    pub = TelegramPublisher(cfg)
    res = pub.publish(JOB, ARTS)
    assert res.state == TargetState.DRY_RUN and res.dry_run
    body = open(res.ref, encoding="utf-8").read()
    assert "ЭТО НЕ ПУБЛИКАЦИЯ" in body
    assert "https://a.example/x" in body        # источники в досье


def test_telegram_live_without_token_is_failure_not_dryrun(cfg):
    cfg.dry_run_publish = False
    cfg.telegram_bot_token = ""
    pub = TelegramPublisher(cfg)
    res = pub.publish(JOB, ARTS)
    assert res.state == TargetState.FAILED
    assert "TELEGRAM_BOT_TOKEN" in res.error


def test_telegram_timeout_gives_uncertain_not_retry(cfg, monkeypatch):
    cfg.dry_run_publish = False
    cfg.telegram_bot_token = "x" * 10
    cfg.tg_out.channel_id = "@test"

    class _FakeTimeout(Exception):
        pass

    _FakeTimeout.__name__ = "ReadTimeout"          # как requests.exceptions.ReadTimeout

    def _timeout(*a, **kw):
        raise _FakeTimeout("имитация обрыва после отправки")

    monkeypatch.setattr("requests.post", _timeout)
    pub = TelegramPublisher(cfg)
    res = pub.publish(JOB, {**ARTS, "telegram_video": __file__})
    assert res.state == TargetState.UNCERTAIN
    assert "возможно" in res.error.lower() or "сверьте" in res.error.lower()


def test_telegram_partial_video_ok_post_fail(cfg, monkeypatch):
    cfg.dry_run_publish = False
    cfg.telegram_bot_token = "x" * 10
    cfg.tg_out.channel_id = "@test"

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"message_id": 42}}

    calls = {"n": 0}

    def _post(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp()          # sendVideo OK
        raise RuntimeError("sendPoll упал")  # опрос упал

    monkeypatch.setattr("requests.post", _post)
    pub = TelegramPublisher(cfg)
    res = pub.publish(JOB, {**ARTS, "telegram_video": __file__})
    # видео+пост могли выйти, опрос нет: состояние честно отражает частичность
    assert res.state in (TargetState.SENT, TargetState.FAILED)
    if res.state == TargetState.SENT:
        assert "опрос не ушёл" in res.error or "пост не ушёл" in res.error


def test_youtube_dry_run_contains_disclosure_fields(cfg):
    cfg.dry_run_publish = True
    pub = YouTubePublisher(cfg)
    res = pub.publish(JOB, ARTS)
    assert res.state == TargetState.DRY_RUN
    body = open(res.ref, encoding="utf-8").read()
    assert "containsSyntheticMedia" in body
    assert "selfDeclaredMadeForKids" in body
    assert "hasCustomThumbnail" not in body   # НЕ disclosure-флаг


def test_youtube_live_without_token_clear_instructions(cfg):
    cfg.dry_run_publish = False
    pub = YouTubePublisher(cfg)
    res = pub.publish(JOB, ARTS)
    assert res.state == TargetState.FAILED
    assert "oauth-youtube" in res.error


def test_youtube_verify_without_credentials_stays_uncertain(cfg):
    pub = YouTubePublisher(cfg)
    res = pub.verify("pub-1", "https://youtu.be/abc123")
    assert res.state == TargetState.UNCERTAIN
    assert "вручную" in res.error


def test_mock_publish_never_called_real_channel(cfg):
    """DRY-RUN не называется успешной публикацией — проверяем формулировки."""
    cfg.dry_run_publish = True
    pub = TelegramPublisher(cfg)
    res = pub.publish(JOB, ARTS)
    body = open(res.ref, encoding="utf-8").read()
    assert "Реальные API не вызывались" in body
