#!/usr/bin/env python3
# ============================================================================
# 03_tts_edge.py — озвучка через Edge-TTS (бесплатно) + тайминги СЛОВ.
# Ключевая идея (Глава 2.4 руководства): Edge-TTS отдаёт события WordBoundary —
# границы каждого слова с точностью 10 мс. Это ЗАМЕНЯЕТ Whisper API для
# караоке-субтитров: таймкоды получаем бесплатно, на лету, из того же стрима.
#
# Выход:
#   tts/voice.mp3        — озвучка 24 кГц mp3
#   tts/words.json       — [{word, start, end}] в секундах
#   tts/stats.json       — длительность/слов для контроля хронометража
#
# Использование:
#   python3 03_tts_edge.py --file script.txt --voice ru-RU-DmitryNeural
#   python3 03_tts_edge.py --text "Проверка синтеза" --rate "+8%"
# ============================================================================
import argparse
import asyncio
import json
import os
import sys


def log(msg: str) -> None:
    print(f"[tts] {msg}", flush=True)


async def synthesize(text: str, voice: str, rate: str, out_dir: str) -> dict:
    """Стримим аудио и параллельно собираем границы слов."""
    import edge_tts  # pip install edge-tts

    os.makedirs(out_dir, exist_ok=True)
    mp3_path = os.path.join(out_dir, "voice.mp3")
    words = []
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")

    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            ctype = chunk.get("type") or chunk.get("Type")
            if ctype == "audio":
                f.write(chunk["data"])
            elif ctype == "WordBoundary":
                # offset и duration приходят в 100-наносекундных единицах
                off = chunk.get("offset") or chunk.get("Offset")
                dur = chunk.get("duration") or chunk.get("Duration")
                txt = chunk.get("text") or chunk.get("Text")
                start_s = off / 1e7
                end_s = (off + dur) / 1e7
                words.append({"word": txt, "start": round(start_s, 3), "end": round(end_s, 3)})

    return {"mp3": mp3_path, "words": words}


def main() -> int:
    ap = argparse.ArgumentParser(description="Edge-TTS озвучка + границы слов")
    ap.add_argument("--text", help="текст сценария прямо в аргументе")
    ap.add_argument("--file", help="текстовый файл сценария (приоритетнее --text)")
    ap.add_argument("--voice", default="ru-RU-DmitryNeural",
                    choices=["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"],
                    help="Dmitry = мужской, Svetlana = женский")
    ap.add_argument("--rate", default="+0%", help="темп, напр. +8%% или -10%%")
    ap.add_argument("--out", default="tts")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read().strip()
    elif args.text:
        text = args.text.strip()
    else:
        ap.error("нужен --file или --text")

    try:
        result = asyncio.run(synthesize(text, args.voice, args.rate, args.out))
    except ImportError:
        print("[tts] ОШИБКА: нет пакета edge-tts. Установите: pip install edge-tts",
              file=sys.stderr)
        return 2
    except Exception as e:  # сетевые сбои Edge-TTS — типичная причина: нет сети
        print(f"[tts] ОШИБКА синтеза (сеть/сервис): {e}", file=sys.stderr)
        return 3

    words = result["words"]
    if not words:
        print("[tts] ОШИБКА: границы слов не получены — обновите edge-tts "
              "(pip install -U edge-tts)", file=sys.stderr)
        return 4

    total = words[-1]["end"]
    with open(os.path.join(args.out, "words.json"), "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=1)
    stats = {
        "voice": args.voice,
        "characters": len(text),
        "words": len(words),
        "duration_s": round(total, 2),
        "words_per_second": round(len(words) / max(total, 0.001), 2),
        "target_short_s": 45,
        "fits_45s": total <= 44.0,
    }
    with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    log(f"озвучено: {stats['words']} слов, {stats['duration_s']} c "
        f"(лимит 45 c: {'OK' if stats['fits_45s'] else 'ПЕРЕБОР — сократите текст'})")
    log(f"темп речи {stats['words_per_second']} слов/с — держите 2.2–2.8 для хуков")
    return 0


if __name__ == "__main__":
    sys.exit(main())
