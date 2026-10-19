r"""Караоке-субтитры .ass из границ слов (WordBoundary) + motion-слои.

v4.1 (обратная связь владельца после первого реального ролика):

1. Строки-ряды вместо переносов libass. Ширина каждого ряда меряется PIL
   (DejaVu Bold, тот же кегль): ряд гарантированно влезает в 940 px ->
   libass НИКОГДА не переносит -> вертикальных наложений букв нет по
   построению. Каждый ряд — отдельное событие с фиксированной позицией
   \an5\pos(540,1458) и лёгким pop-масштабом (\t).
2. Сброс строки строго по границам предложений и паузам: слова двух
   предложений НИКОГДА не попадают в один ряд (границы — те же, что у
   сцен: scenes.sentence_word_spans); пауза >= 0.35 c — тоже сброс.
3. Motion-слои (libass, дёшево для VA-API/CPU):
   - Layer 4: тонкая полоска прогресса выпуска (трек + шагающий fill);
   - Layer 3: кинетическая типографика — номер дела / ключевая цифра
     с pop scale-up и overshoot, либо плавно въезжающая плашка-бейдж
     («Решение суда», «Стороны спора», «Факт N», ...).

Читаемость (сохранено из rc1): крупный жирный шрифт 64, плотная обводка,
MarginV 430 (над UI плеера); подсветка активного слова акцентом.
"""
from __future__ import annotations

import re
from pathlib import Path

# ------------------------------------------------------------------ константы

ROW_Y = 1458            # вертикальный центр ряда субтитров (PlayRes 1080x1920)
MAX_ROW_PX = 940        # гарантированная ширина ряда (не переносится libass)
PAUSE_SPLIT_S = 0.35    # пауза между словами, сбрасывающая строку
BADGE_Y = 210           # слот кинетики/бейджа (под прогресс-баром)
PROG_X0, PROG_X1, PROG_H, PROG_Y = 90, 990, 6, 100   # полоска прогресса
PROG_STEP_S = 0.5       # шаг fill-полоски

_DEFAULT_BOLDFONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# цвет ASS: &HAABBGGRR (alpha: 00 = непрозрачно, FF = прозрачно)
_C_CYAN = "&H00EED322"        # акцент (34,211,238)
_C_WHITE = "&H00FFFFFF"
_C_PLATE = "&H30101A20"       # тёмно-синяя плашка, почти непрозрачная
_C_PLATE_SOFT = "&H50101A20"
_C_TRACK = "&H60B8A394"       # серый трек прогресса, полупрозрачный
_C_PURPLE = "&H00FA8BA7"      # фиолетовый акцент (167,139,250)


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


# ------------------------------------------------------------------ измерение

_font_cache: dict = {}


def _pil_font(font_path: str | None, size: int):
    """PIL-шрифт для измерения ширины ряда; None — шрифт недоступен."""
    if not font_path or not Path(font_path).exists():
        return None
    key = (font_path, size)
    if key not in _font_cache:
        from PIL import ImageFont
        _font_cache[key] = ImageFont.truetype(font_path, size)
    return _font_cache[key]


def _row_width_px(row: list, measurer) -> float:
    """Ширина текста ряда в пикселях (measurer без шрифта -> 0, без лимита)."""
    if measurer is None or not measurer.ok:
        return 0.0
    text = " ".join(_esc(w["word"]) for w in row)
    return measurer.font.getlength(text)


class _Measurer:
    def __init__(self, font_path: str | None, size: int):
        self.font = _pil_font(font_path, size)
        self.ok = self.font is not None


def _sentence_ids(words: list, spans: list | None) -> list:
    """Каждому слову — индекс предложения (по spans или по пунктуации)."""
    if spans:
        ids = [0] * len(words)
        for s_i, (i, j) in enumerate(spans):
            for k in range(i, min(j, len(words))):
                ids[k] = s_i
        return ids
    # fallback: границы по знакам конца предложения в самих словах
    ids, cur = [], 0
    for w in words:
        ids.append(cur)
        if re.search(r"[.!?…]$", _esc(w["word"])):
            cur += 1
    return ids


def _pack_rows(words: list, measurer, sentence_ids: list,
               max_words: int = 4, max_dur: float = 2.4,
               pause_s: float = PAUSE_SPLIT_S, max_px: float = MAX_ROW_PX) -> list:
    """Слова -> ряды-строки.

    Правила сброса строки: новое предложение; пауза >= pause_s; лимит
    слов/длительности; ширина ряда > max_px (измерено PIL -> libass не
    переносит -> наложений при переносе нет по построению).
    """
    rows, cur = [], []
    for i, w in enumerate(words):
        if cur:
            gap = w["start"] - cur[-1]["end"]
            too_many = len(cur) >= max_words
            too_long = (w["end"] - cur[0]["start"]) > max_dur
            new_sent = sentence_ids[i] != sentence_ids[i - 1]
            too_wide = measurer.ok and _row_width_px(cur + [w], measurer) > max_px
            if new_sent or gap >= pause_s or too_many or too_long or too_wide:
                rows.append(cur)
                cur = []
        cur.append(w)
    if cur:
        rows.append(cur)
    return rows


# ------------------------------------------------------------------ караоке

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


# два блока тегов: fad замкнут (совместимость с парсером v4.0), затем
# позиция ряда + pop-анимация
_ROW_TAGS = ( "{\\fad(100,100)}"
              "{\\an5\\pos(540,%d)\\fscx94\\fscy94"
              "\\t(0,140,\\fscx100\\fscy100)}" % ROW_Y )


# ------------------------------------------------------------------ оверлеи

def _badge_event(text: str, t0: float, t1: float) -> str:
    """Плашка-бейдж: плавный въезд слева + scale-settle, непрозрачная основа."""
    tags = ("{\\fad(150,180)\\an5\\move(190,%d,540,%d,0,420)"
            "\\fscx84\\fscy84\\t(0,300,\\fscx100\\fscy100)}" % (BADGE_Y, BADGE_Y))
    return ("Dialogue: 3,%s,%s,Badge,,0,0,0,,%s%s"
            % (_ts(t0), _ts(t1), tags, _esc(text)))


def _kinetic_event(text: str, t0: float, t1: float) -> str:
    """Кинетическая типографика: pop scale-up с overshoot (номер дела, цифра)."""
    tags = ("{\\fad(100,200)\\an5\\pos(540,%d)"
            "\\fscx78\\fscy78\\t(0,200,\\fscx108\\fscy108)"
            "\\t(200,340,\\fscx100\\fscy100)}" % BADGE_Y)
    return ("Dialogue: 3,%s,%s,Kinetic,,0,0,0,,%s%s"
            % (_ts(t0), _ts(t1), tags, _esc(text)))


def _rect_draw(width_px: int, style: str, t0: float, t1: float) -> str:
    r"""Прямоугольник векторной графики libass (\\p1)."""
    w = max(1, int(round(width_px)))
    return ("Dialogue: 4,%s,%s,%s,,0,0,0,,{\\p1\\an7\\pos(%d,%d)}"
            "m 0 0 l %d 0 l %d %d l 0 %d{\\p0}"
            % (_ts(t0), _ts(t1), style, PROG_X0, PROG_Y,
               w, w, PROG_H, PROG_H))


def _progress_events(total: float) -> list:
    """Тонкая полоска прогресса: серый трек + шагающий акцентный fill.

    Ширина fill берётся по КОНЦУ сегмента — к финалу полоска гарантированно
    заполнена до конца (последний сегмент = 100%).
    """
    if total <= 0:
        return []
    events = [_rect_draw(PROG_X1 - PROG_X0, "ProgressTrack", 0.0, total)]
    span = PROG_X1 - PROG_X0
    t = 0.0
    while t < total - 0.01:
        t1 = min(total, t + PROG_STEP_S)
        frac = min(1.0, t1 / total)
        events.append(_rect_draw(span * frac, "ProgressFill", t, t1))
        t = t1
    return events


def _scene_overlay_events(scenes: list, total: float) -> list:
    """Кинетика/бейджи по сценам. Приоритет: kinetic (номер/цифра) > badge."""
    events: list = []
    for sc in scenes:
        d = sc.to_dict() if hasattr(sc, "to_dict") else dict(sc)
        t0 = float(d.get("start", 0.0)) + 0.30
        t1 = min(total - 0.05, float(d.get("end", 0.0)) - 0.25)
        if t1 - t0 < 0.5:
            continue
        text = str(d.get("kinetic") or "").strip()
        if text:
            events.append(_kinetic_event(text, t0, t1))
        else:
            badge = str(d.get("badge") or "").strip()
            if badge:
                events.append(_badge_event(badge, t0, t1))
    return events


# ------------------------------------------------------------------ сборка

def _styles(font: str) -> str:
    karaoke_style = (
        f"Style: Karaoke,{font},64,{_C_CYAN},{_C_WHITE},&H00000000,&HA0000000,"
        f"-1,0,0,0,100,100,0,0,1,5,2,2,56,56,430,1")
    top_style = (
        f"Style: Top,{font},58,{_C_WHITE},{_C_WHITE},&H00202020,&H90000000,"
        f"-1,0,0,0,100,100,1,0,1,4,2,8,60,60,300,1")
    # бейдж: непрозрачная плашка (BorderStyle=3), поля бокса задаёт Outline
    badge_style = (
        f"Style: Badge,{font},44,{_C_WHITE},{_C_WHITE},{_C_PLATE},{_C_PLATE},"
        f"-1,0,0,0,100,100,1,0,3,14,0,5,20,20,180,1")
    # кинетика: крупный акцентный номер/цифра на тёмной плашке
    kinetic_style = (
        f"Style: Kinetic,{font},54,{_C_CYAN},{_C_CYAN},{_C_PLATE},{_C_PLATE},"
        f"-1,0,0,0,100,100,1.04,1.04,0,3,16,0,5,20,20,180,1")
    # полоска прогресса: рисование \p, важен только PrimaryColour
    track_style = (
        f"Style: ProgressTrack,{font},10,{_C_TRACK},{_C_TRACK},{_C_TRACK},{_C_TRACK},"
        f"0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1")
    fill_style = (
        f"Style: ProgressFill,{font},10,{_C_CYAN},{_C_CYAN},{_C_CYAN},{_C_CYAN},"
        f"0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1")
    return "\n".join([karaoke_style, top_style, badge_style, kinetic_style,
                      track_style, fill_style])


def build_ass(words: list, hook: str, out_path: Path, font: str = "DejaVu Sans",
              play_res: tuple = (1080, 1920), sentence_spans: list | None = None,
              scenes: list | None = None, total: float | None = None,
              font_bold_path: str | None = None) -> Path:
    """Собирает .ass: караоке-ряды + motion-слои. Возвращает путь."""
    if not words:
        raise ValueError("build_ass: пустой список слов")
    voice_end = words[-1]["end"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    measurer = _Measurer(font_bold_path or _DEFAULT_BOLDFONT, 64)
    sentence_ids = _sentence_ids(words, sentence_spans)
    rows = _pack_rows(words, measurer, sentence_ids)

    header = f"""[Script Info]
; Tubecook v4.1 — караоке-ряды (без переносов libass) + motion-слои
ScriptType: v4.00+
PlayResX: {play_res[0]}
PlayResY: {play_res[1]}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{_styles(font)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    hook_txt = _esc(hook or "")
    if hook_txt:
        # хук живёт сверху первые ~3.2 c и не пересекается с караоке-блоком
        events.append("Dialogue: 1,%s,%s,Top,,0,0,0,,{\\fad(250,350)}%s"
                      % (_ts(0.0), _ts(3.2), hook_txt))

    prev_end = 0.0
    for idx, line in enumerate(rows):
        next_start = rows[idx + 1][0]["start"] if idx + 1 < len(rows) else None
        start, end, text = _karaoke_line(line, next_start, prev_end, voice_end)
        prev_end = end
        events.append("Dialogue: 0,%s,%s,Karaoke,,0,0,0,,%s%s"
                      % (_ts(start), _ts(end), _ROW_TAGS, text))

    # motion-слои: прогресс-бар + кинетика/бейджи
    if total and total > 0:
        events.extend(_progress_events(total))
    if scenes:
        events.extend(_scene_overlay_events(scenes, total or voice_end + 0.9))

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def ass_coverage(words: list) -> tuple:
    """(первый старт строки, последний конец) для проверок покрытия."""
    return (words[0]["start"], words[-1]["end"]) if words else (0.0, 0.0)
