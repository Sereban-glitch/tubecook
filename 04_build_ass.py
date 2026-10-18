#!/usr/bin/env python3
# ============================================================================
# 04_build_ass.py — караоке-субтитры .ass из границ слов (tts/words.json).
# Формула удержания (Глава 4.4): активное слово подсвечивается ровно в момент
# произношения — глаз «читает за голосом», удержание 3-сек окна растёт на 8-15%.
#
# Стратегия группировки: строка = максимум 3 слова ИЛИ 2.2 с (что раньше).
# Стили:
#   Karaoke — нижний блок, выравнивание 2, MarginV 320 (над UI плеера)
#   Top     — хук-заголовок первых 3 секунд, выравнивание 8
# Подсветка: {\kNN} в сотых секунды от начала строки (стандарт libass).
#
# Использование:
#   python3 04_build_ass.py --words tts/words.json --hook "Математика позволит украсть вселенную"
# ============================================================================
import argparse
import json
import math
import os
import sys


def ts(sec: float) -> str:
    """Секунды -> '0:00:03.25' (формат .ass)."""
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(text: str) -> str:
    """Убираем фигурные скобки — иначе сломают разметку .ass."""
    return text.replace("{", "").replace("}", "").replace("\n", " ").strip()


def chunk_words(words: list, max_words: int = 3, max_dur: float = 2.2) -> list:
    """Режим поток слов на экраны: короткие строки быстрее читаются в Shorts."""
    lines, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or (w["end"] - cur[0]["start"]) > max_dur):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def karaoke_line(line: list, next_start: float | None, prev_end: float) -> tuple:
    r"""(start, end, текст) одной строки: тег \k задаётся для каждого слова по его длительности."""
    start = max(line[0]["start"], prev_end + 0.02)
    if next_start is not None:
        tail = min(0.25, max(0.0, next_start - line[-1]["end"]))
    else:
        tail = 0.25
    end = line[-1]["end"] + tail
    parts = []
    cur_t = start
    for w in line:
        gap = max(0, round((w["start"] - cur_t) * 100))
        dur = max(1, round((w["end"] - w["start"]) * 100))
        if gap > 0:
            parts.append("{\\k%d}" % gap)
        parts.append("{\\k%d}%s" % (dur, esc(w["word"])))
        cur_t = w["end"]
    return start, end, " ".join(parts)


def get_ass_header(style: str = "standard") -> str:
    if style == "cinematic":
        # Cinematic / Hormozi style: золотая подсветка активного слова (&H0000D7FF), белый текст (&H00FFFFFF), густая обводка и safe-zone MarginV=380
        karaoke_line_style = "Style: Karaoke,DejaVu Sans,96,&H0000D7FF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,5,3,2,60,60,380,1"
        top_style = "Style: Top,DejaVu Sans,100,&H0000D7FF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,1,5,3,8,50,50,300,1"
    else:
        karaoke_line_style = "Style: Karaoke,DejaVu Sans,92,&H00FFFFFF,&H50FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,320,1"
        top_style = "Style: Top,DejaVu Sans,104,&H00FFFFFF,&H50FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,5,3,8,50,50,300,1"

    return f"""[Script Info]
; Сгенерировано 04_build_ass.py — караоке-субтитры Shorts 1080x1920 ({style})
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{karaoke_line_style}
{top_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Караоке .ass из words.json")
    ap.add_argument("--words", default="tts/words.json")
    ap.add_argument("--hook", required=True, help="хук первых 3 секунд (титул сверху)")
    ap.add_argument("--style", default="standard", choices=["standard", "cinematic"], help="стиль субтитров")
    ap.add_argument("--out", default="subs/short.ass")
    args = ap.parse_args()

    with open(args.words, encoding="utf-8") as f:
        words = json.load(f)
    if not words:
        print("[ass] ОШИБКА: words.json пуст", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    events = []

    # 1) Хук: 0.0 - 3.0 c, стиль Top, мягкое появление/уход
    hook_txt = esc(args.hook)
    if hook_txt:
        events.append(
            "Dialogue: 1,%s,%s,Top,,0,0,0,,{\\fad(250,350)}%s"
            % (ts(0.0), ts(3.0), hook_txt)
        )

    # 2) Основные строки караоке (без перекрытий: хвост vs начало следующей)
    chunks = chunk_words(words)
    prev_end = 0.0
    for idx, line in enumerate(chunks):
        next_start = chunks[idx + 1][0]["start"] if idx + 1 < len(chunks) else None
        start, end, text = karaoke_line(line, next_start, prev_end)
        prev_end = end
        events.append(
            "Dialogue: 0,%s,%s,Karaoke,,0,0,0,,{\\fad(120,120)}%s"
            % (ts(start), ts(end), text)
        )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(get_ass_header(args.style))
        f.write("\n".join(events) + "\n")

    n = len(events) - (1 if hook_txt else 0)
    print(f"[ass] готово: {args.out} — {n} строк караоке + хук")
    print(f"[ass] покрытие: {ts(0.0)} - {ts(words[-1]['end'])} (по words.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
