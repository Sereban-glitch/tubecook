"""Утилиты запуска ffmpeg/ffprobe + честные проверки длительностей.

Правило ТЗ: никогда не используем -shortest (он обрезал финальную фразу в v3).
Длительности всегда сверяются ffprobe-ом ПОСЛЕ рендера; расхождение — ошибка.
"""
from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path


class FFError(RuntimeError):
    pass


def run(cmd: list, stage: str = "ffmpeg", cwd: str | None = None,
        timeout: int = 3600) -> str:
    cmd = [str(c) for c in cmd]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    if p.returncode != 0:
        tail = (p.stderr or p.stdout)[-2000:]
        raise FFError(f"[{stage}] exit={p.returncode}: {tail}")
    return f"[{stage}] {time.time() - t0:.1f} c"


def probe(path) -> dict:
    """format/streams сводка ffprobe."""
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,width,height,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def probe_duration(path) -> float:
    return float(probe(path)["format"]["duration"])


def size_mb(path) -> float:
    return Path(path).stat().st_size / (1024 * 1024)


def env_report() -> dict:
    """Честные сведения о среде, в которой реально шёл рендер."""
    info = {
        "python": platform.python_version(),
        "system": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": __import__("os").cpu_count(),
        "vaapi_device": None,
    }
    try:
        import os
        if Path("/dev/dri/renderD128").exists():
            info["vaapi_device"] = "/dev/dri/renderD128"
    except Exception:
        pass
    return info


def assert_tail(vdur: float, adur: float, speech_end: float, tail_s: float,
                tol: float = 0.45) -> None:
    """Гарантия «финальная мысль не обрывается»:
    видео >= конец речи + (tail - tol); аудио не длиннее видео;
    видео не аномально длиннее звука (защита от расхождения сцен).
    """
    if vdur < speech_end + tail_s - tol:
        raise FFError(
            f"финал обрезан: видео {vdur:.2f} c < речь+хвост "
            f"{speech_end + tail_s:.2f} c (tol {tol})")
    if adur > vdur + 0.05:
        raise FFError(f"аудио ({adur:.2f} c) длиннее видео ({vdur:.2f} c) — "
                      "риск обрезания последней фразы")
    if vdur > max(adur, speech_end + tail_s) + 5.0:
        raise FFError(f"видео аномально длинное ({vdur:.2f} c) относительно звука "
                      f"({adur:.2f} c) — проверьте длительности сцен")


def assert_no_shortest(cmd: list) -> None:
    flat = [str(c) for c in cmd]
    if "-shortest" in flat:
        raise FFError("запрещённый флаг -shortest в команде рендера")
