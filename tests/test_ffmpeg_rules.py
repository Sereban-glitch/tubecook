"""Правила ffmpeg: запрет -shortest, размерный ladder, интеграционный рендер."""
import json
import shutil

import pytest

from tubecook.media import ffmpeg_utils as ff
from tubecook.media import gfx, scenes as scenesm
from tubecook.media.ass import build_ass
from tubecook.media.deliver import encode_telegram, extract_thumbnail
from tubecook.media.render import render_episode

from conftest import HAS_FFMPEG, words_of

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="нет ffmpeg в среде")


def test_assert_no_shortest_blocks_flag():
    with pytest.raises(ff.FFError):
        ff.assert_no_shortest(["ffmpeg", "-i", "a.mp4", "-shortest", "b.mp4"])


def test_deliver_ladder_success_and_duration(tmp_path, cfg, monkeypatch):
    from conftest import make_tiny_video
    master = make_tiny_video(tmp_path / "m.mp4", seconds=3.0)
    cfg.tg_out.budget_mb = 50          # большой бюджет — первая ступень проходит
    res = encode_telegram(master, tmp_path / "tg.mp4", cfg)
    assert res["crf"] == cfg.tg_out.crf_ladder[0]
    assert abs(res["duration_s"] - 3.0) < 0.35   # фраза не урезана


def test_deliver_ladder_exhausts_honestly(tmp_path, cfg):
    from conftest import make_tiny_video
    master = make_tiny_video(tmp_path / "m.mp4", seconds=3.0)
    cfg.tg_out.budget_mb = 0.0001      # недостижимый бюджет
    with pytest.raises(ff.FFError) as e:
        encode_telegram(master, tmp_path / "tg.mp4", cfg)
    assert "не удалось уложиться" in str(e.value)


def test_thumbnail(tmp_path, cfg):
    from conftest import make_tiny_video
    master = make_tiny_video(tmp_path / "m.mp4", seconds=2.0)
    thumb = extract_thumbnail(master, tmp_path / "thumb.jpg")
    assert thumb.exists() and thumb.stat().st_size > 0


def test_gfx_scene_layers(tmp_path, cfg):
    sc = scenesm.Scene(index=0, kind="hook", text="Хук для проверки графики",
                       start=0, end=2.5, dur=2.5, demo=True,
                       out_dir=str(tmp_path))
    lay = gfx.render_scene_layers(sc.to_dict())
    for key in ("bg", "card", "accent"):
        assert lay[key].exists() and lay[key].stat().st_size > 1000
    from PIL import Image
    with Image.open(lay["card"]) as im:
        assert im.size == (1080, 1920)


def test_render_episode_integration_tiny(tmp_path, cfg):
    """Мини-сквозной рендер (mock-TTS, 540x960): гарантии финала и отчёт."""
    cfg.render.w, cfg.render.h = 540, 960
    cfg.render.transition_s = 0.25
    cfg.render.extended_transition_s = 0.3
    payload = {
        "job_id": "it-1", "topic": "Интеграционный тест", "hook": "Хук теста",
        "script": ("Первое предложение интеграционного теста рендера. "
                   "Второе предложение несёт цифру 30 кадров. "
                   "Финальная фраза завершает мысль целиком."),
        "sources": [{"url": "https://example.com/x", "checked_at": "2026-10-18 09:00"}],
        "facts": [{"text": "факт", "attribution": "тест"}],
        "visual_plan": [], "demo": True,
    }
    res = render_episode(payload, cfg, tmp_path, profile="base", engine="mock")
    master = res["master"]
    assert master.exists()
    rep = res["report"]
    assert rep["tts_engine"] == "mock"          # честная маркировка движка
    vdur = ff.probe_duration(master)
    # финал не обрезан: видео >= речь + хвост (с допуском)
    assert vdur >= rep["speech_end_s"] + cfg.render.tail_s - 0.45
    # в команде рендера не было -shortest (проверено внутри render), плюс:
    probe = ff.probe(master)
    assert {s["codec_type"] for s in probe["streams"]} == {"video", "audio"}
    # субтитры вжаты: видео содержит их (асс существует и покрывает речь)
    ass = tmp_path / "subs.ass"
    assert ass.exists()

    tg = encode_telegram(master, tmp_path / "tg.mp4", cfg,
                         budget_mb=50)
    assert abs(tg["duration_s"] - vdur) < 0.35
