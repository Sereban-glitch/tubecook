r"""Караоке-субтитры .ass из границ слов (WordBoundary).

Отличия от v3:
- читаемость на телефоне: крупный жирный шрифт, плотная обводка, MarginV 430
  (над UI плеера), строки максимум 4 слова / 2.4 c;
- подсветка активного слова ровно в момент произношения: несённое слово
  окрашивается акцентом (PrimaryColour), ещё не прозвучавшее — белым;
- хук-заголовок сверху с мягким появлением, вне зоны субтитров;
- длительности \k считаются от начала строки, включая паузы между словами.
"""
from __future__ import annotations

import re
from pathlib import Path


def _ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _chunk_words(words: list, max_words: int = 4, max_dur: float = 2.4) -> list:
    lines, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or (w["end"] - cur[0]["start"]) > max_dur):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _karaoke_line(line: list, next_start: float | None, prev_end: float,
                  voice_end: float) -> tuple:
    start = max(line[0]["start"] - 0.12, prev_end + 0.02, 0.0)
    if next_start is not None:
        tail = min(0.28, max(0.0, next_start - line[-1]["end"]))
    else:
        tail = 0.28
    end = min(line[-1]["end"] + tail, voice_end + 0.2)
    parts = []
    cur_t = start
    for w in line:
        gap = max(0, round((w["start"] - cur_t) * 100))
        dur = max(1, round((w["end"] - w["start"]) * 100))
        if gap > 0:
            parts.append("{\\k%d}" % gap)
        parts.append("{\\k%d}%s" % (dur, _esc(w["word"])))
        cur_t = w["end"]
    return start, end, " ".join(parts)


def build_ass(words: list, hook: str, out_path: Path, font: str = "DejaVu Sans",
              play_res: tuple = (1080, 1920)) -> Path:
    """Собирает .ass. Возвращает путь (и пишет файл)."""
    if not words:
        raise ValueError("build_ass: пустой список слов")
    voice_end = words[-1]["end"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # цвета: Primary = уже прозвучало (акцент циан), Secondary = ещё нет (белый)
    karaoke_style = (
        f"Style: Karaoke,{font},64,&H00EED322,&H00FFFFFF,&H00000000,&HA0000000,"
        "-1,0,0,0,100,100,0,0,1,5,2,2,56,56,430,1")
    top_style = (
        f"Style: Top,{font},58,&H00FFFFFF,&H00FFFFFF,&H00202020,&H90000000,"
        "-1,0,0,0,100,100,1,0,1,4,2,8,60,60,300,1")

    header = f"""[Script Info]
; Tubecook v4 — караоке-субтитры, синхронные с WordBoundary
ScriptType: v4.00+
PlayResX: {play_res[0]}
PlayResY: {play_res[1]}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{karaoke_style}
{top_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    hook_txt = _esc(hook or "")
    if hook_txt:
        # хук живёт сверху первые ~3.2 c и не пересекается с караоке-блоком
        events.append("Dialogue: 1,%s,%s,Top,,0,0,0,,{\\fad(250,350)}%s"
                      % (_ts(0.0), _ts(3.2), hook_txt))

    chunks = _chunk_words(words)
    prev_end = 0.0
    for idx, line in enumerate(chunks):
        next_start = chunks[idx + 1][0]["start"] if idx + 1 < len(chunks) else None
        start, end, text = _karaoke_line(line, next_start, prev_end, voice_end)
        prev_end = end
        events.append("Dialogue: 0,%s,%s,Karaoke,,0,0,0,,{\\fad(100,100)}%s"
                      % (_ts(start), _ts(end), text))

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def ass_coverage(words: list) -> tuple:
    """(первый старт строки, последний конец) для проверок покрытия."""
    return (words[0]["start"], words[-1]["end"]) if words else (0.0, 0.0)
