"""BGM v4.1: категории подложки, выбор через TUBECOOK_BGM, баланс даккинга."""
import wave
from pathlib import Path

import pytest

from tubecook.config import Config
from tubecook.media import render as R

REPO = Path(__file__).resolve().parent.parent


def _tiny_wav(path: Path, seconds: float = 2.0) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00\x00\x00" * int(44100 * seconds))
    return path


# ------------------------------------------------------------------ ассеты

@pytest.mark.parametrize("cat", ["news", "legal", "tech"])
def test_bgm_assets_present(cat):
    """Три нейтральные подложки лежат в репозитории и не пустые."""
    p = REPO / "assets" / "bgm" / f"{cat}_loop.mp3"
    assert p.exists(), f"нет {p} — запустите scripts/make_bgm.py"
    assert p.stat().st_size > 100 * 1024   # > 100 КиБ реального аудио


def test_bgm_synth_deterministic_and_loudness():
    """Синтезатор детерминирован, ~32 c, пик около -12 dBFS."""
    import numpy as np
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    from make_bgm import make_track, SR

    a = make_track("news")
    b = make_track("news")
    assert a.tobytes() == b.tobytes()       # одинаково на любой машине

    dur = len(a) / 2 / SR
    assert 28.0 <= dur <= 36.0              # целое число тактов ~32 c

    mono = np.frombuffer(a.tobytes(), dtype=np.int16).astype(float)
    peak_db = 20 * float(np.log10(max(1.0, np.abs(mono).max()) / 32768))
    assert -13.5 <= peak_db <= -11.0        # нормализация к -12 dBFS


# ------------------------------------------------------------------ конфиг

def test_bgm_config_categories(monkeypatch, tmp_path):
    monkeypatch.setenv("TUBECOOK_BGM", "legal")
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_path is not None
    assert cfg.bgm_path.name == "legal_loop.mp3"
    assert cfg.bgm_category == "legal"


def test_bgm_config_default_news(monkeypatch, tmp_path):
    monkeypatch.delenv("TUBECOOK_BGM", raising=False)
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_path is not None
    assert cfg.bgm_path.name == "news_loop.mp3"     # мрачный legacy не по умолчанию


def test_bgm_config_none_disables(monkeypatch, tmp_path):
    monkeypatch.setenv("TUBECOOK_BGM", "none")
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_path is None
    assert cfg.bgm_category == "none"


def test_bgm_config_custom_path(monkeypatch, tmp_path):
    custom = tmp_path / "my_bed.mp3"
    monkeypatch.setenv("TUBECOOK_BGM", str(custom))
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_path == custom
    assert cfg.bgm_category == str(custom)


def test_bgm_volume_clamped(monkeypatch, tmp_path):
    monkeypatch.setenv("TUBECOOK_BGM_VOLUME", "7.5")
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_volume == 1.5
    monkeypatch.setenv("TUBECOOK_BGM_VOLUME", "-2")
    cfg = Config.from_env(root=tmp_path)
    assert cfg.bgm_volume == 0.0


# ------------------------------------------------------------------ даккинг

class _FakeProc:
    def __init__(self):
        self.stderr = ('{ "input_i" : "-18.4", "input_tp" : "-1.9", '
                       '"input_lra" : "8.2", "input_thresh" : "-28.7", '
                       '"target_offset" : "0.4" }')


def test_ducking_graph_voice_crystal_music_light(monkeypatch, tmp_path):
    """Граф даккинга: highpass на музыке, ratio=12, bed-громкость из конфига."""
    voice = _tiny_wav(tmp_path / "voice.wav")
    bgm = _tiny_wav(tmp_path / "bgm.wav")
    calls = []

    def fake_run(args, stage):
        calls.append(" ".join(str(a) for a in args))
        return _FakeProc()

    monkeypatch.setattr(R, "_run_ffmpeg", fake_run)
    R._render_audio(voice, bgm, 12.0, tmp_path, bgm_volume=0.5)

    assert len(calls) == 2                       # замер + финал
    g = [c for c in calls if "-filter_complex" in c][0]
    fc = g.split("-filter_complex", 1)[1].split(" -map")[0].strip(" ")
    assert "highpass=f=180" in fc                 # музыка не мутит частоты диктора
    assert "volume=0.500" in fc                   # bed-громкость конфигурируется
    assert "sidechaincompress=threshold=0.02:ratio=12:attack=8:release=280" in fc
    assert "amix=inputs=2:duration=first:normalize=0" in fc   # голос не ослабляется
    # голос идёт чистым путём: в его цепочке [0:a] нет ни volume, ни highpass
    voice_chain = fc.split(";")[0]
    assert voice_chain.startswith("[0:a]")
    assert "volume" not in voice_chain and "highpass" not in voice_chain


def test_ducking_absent_without_bgm(monkeypatch, tmp_path):
    voice = _tiny_wav(tmp_path / "voice.wav")
    calls = []

    def fake_run(args, stage):
        calls.append(" ".join(str(a) for a in args))
        return _FakeProc()

    monkeypatch.setattr(R, "_run_ffmpeg", fake_run)
    R._render_audio(voice, None, 12.0, tmp_path)     # bgm отключен
    g = [c for c in calls if "-filter_complex" in c][0]
    assert "sidechaincompress" not in g
    assert "amix" not in g
