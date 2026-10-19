"""Доставка: Telegram-версия 540x960 до 15 МБ + миниатюра.

Размерный ladder: CRF 23 -> 26 -> 28 (аудио 128 -> 96 -> 80k). Повторный
encode НЕ урезает фразу: длительности сохраняются, проверяется ffprobe.
"""
from __future__ import annotations

from pathlib import Path

from tubecook.media import ffmpeg_utils as ff


def encode_telegram(master: Path, out: Path, cfg, budget_mb: float | None = None) -> dict:
    budget = budget_mb or cfg.tg_out.budget_mb
    crfs = list(cfg.tg_out.crf_ladder) + [30]
    auds = list(cfg.tg_out.audio_k_ladder) + [64]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    chosen = None
    for crf, ab in zip(crfs, auds):
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(master),
               "-vf", "scale=540:960:flags=lanczos",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
               "-c:a", "aac", "-b:a", f"{ab}k",
               "-movflags", "+faststart", str(out)]
        ff.assert_no_shortest(cmd)
        ff.run(cmd, f"tg_encode_crf{crf}")
        size = ff.size_mb(out)
        if size <= budget * 0.97:
            chosen = {"crf": crf, "audio_k": ab, "size_mb": round(size, 2)}
            break
    if chosen is None:
        raise ff.FFError(
            f"не удалось уложиться в {budget} МБ (последняя попытка "
            f"{ff.size_mb(out):.1f} МБ); проверьте длительность сценария")

    # длительности обязаны совпасть с мастером (фраза не обрезается)
    md, td = ff.probe_duration(master), ff.probe_duration(out)
    if abs(md - td) > 0.35:
        raise ff.FFError(f"telegram-версия исказила длительность: "
                         f"{td:.2f} c вместо {md:.2f} c")
    chosen["duration_s"] = round(td, 2)
    return {"path": out, **chosen}


def extract_thumbnail(master: Path, out: Path, at_frac: float = 0.4) -> Path:
    dur = ff.probe_duration(master)
    at = max(0.1, dur * at_frac)
    out = Path(out)
    ff.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{at:.2f}", "-i", str(master), "-frames:v", "1",
            "-q:v", "3", str(out)], "thumb")
    return out
