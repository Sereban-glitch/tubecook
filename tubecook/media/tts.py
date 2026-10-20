"""Озвучка: Edge-TTS (основной путь) + детерминированный мок (оффлайн/тесты).

Edge-TTS бесплатно отдаёт WordBoundary — границы каждого слова с точностью
~10 мс, что даёт караоке-субтитры без Whisper и с нулевой погрешностью
тайминга (подход v3 сохранён). Кэш по (текст+голос+темп) экономит квоту
и ускоряет повторные рендеры.

Мок: тишина + слова с эвристическими таймингами. Используется в тестах и
когда сети нет. В отчёте рендера честно указывается движок (edge|mock|cache) —
мок никогда не выдаётся за реальную озвучку.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TTSResult:
    path: str
    words: list           # [{word, start, end}] в секундах
    speech_end: float     # конец последнего слова
    engine: str           # edge | mock | cache


class TTSError(RuntimeError):
    pass


async def _edge_synthesize(text: str, voice: str, rate: str, out_path: Path) -> list:
    import edge_tts
    words: list = []
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                f.write(chunk["data"])
            elif ctype == "WordBoundary":
                off = (chunk.get("offset") or 0) / 1e7
                dur = (chunk.get("duration") or 0) / 1e7
                words.append({"word": chunk.get("text") or "",
                              "start": round(off, 3),
                              "end": round(off + dur, 3)})
    if not words:
        raise TTSError("edge-tts: границы слов не получены (обновите edge-tts)")
    return words


def _mock_durations(text: str) -> list:
    """Детерминированные тайминги: 90мс + 58мс/букву, пауза на знаках."""
    words: list = []
    t = 0.08
    for raw in text.split():
        clean = raw.strip()
        dur = min(0.75, 0.09 + 0.058 * max(len(re.sub(r"[^\w]", "", clean)), 1))
        words.append({"word": clean, "start": round(t, 3),
                      "end": round(t + dur, 3)})
        t += dur + (0.22 if clean.endswith((".", "!", "?", "…")) else
                    0.10 if clean.endswith((",", ";", ":")) else 0.045)
    return words


def _mock_wav(path: Path, total_s: float, sample_rate: int = 24000) -> None:
    n = int(total_s * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)


def synthesize(text: str, cfg, out_dir: Path, engine: str = "auto") -> TTSResult:
    """Синтез с кэшем. engine: auto | edge | mock."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{text}|{cfg.voice}|{cfg.rate}".encode()).hexdigest()[:16]

    if engine in ("auto", "edge"):
        mp3 = out_dir / f"voice_{key}.mp3"
        words_f = out_dir / f"words_{key}.json"
        if words_f.exists() and mp3.exists() and mp3.stat().st_size > 1000 and words_f.stat().st_size > 10:
            try:
                words = json.loads(words_f.read_text(encoding="utf-8"))
                if words:
                    return TTSResult(str(mp3), words, words[-1]["end"], engine="cache")
            except Exception:
                pass
        
        import time
        last_err = None
        for attempt in range(3):
            tmp_mp3 = out_dir / f"voice_{key}.tmp.mp3"
            try:
                words = asyncio.run(_edge_synthesize(text, cfg.voice, cfg.rate, tmp_mp3))
                if tmp_mp3.exists() and tmp_mp3.stat().st_size > 1000 and words:
                    tmp_mp3.replace(mp3)
                    words_f.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
                    return TTSResult(str(mp3), words, words[-1]["end"], engine="edge")
            except ImportError as e:
                last_err = e
                break
            except Exception as e:
                last_err = e
                if tmp_mp3.exists():
                    try:
                        tmp_mp3.unlink()
                    except Exception:
                        pass
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
        
        if engine == "edge":
            raise TTSError(f"edge-tts сбой: {last_err}")

    # мок: тишина + эвристические тайминги (только тесты/оффлайн)
    words = _mock_durations(text)
    if not words:
        raise TTSError("пустой сценарий: нечего озвучивать")
    total = words[-1]["end"] + 0.3
    wav = out_dir / f"voice_{key}.wav"
    _mock_wav(wav, total)
    wf = out_dir / f"words_{key}.json"
    wf.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return TTSResult(str(wav), words, words[-1]["end"], engine="mock")
