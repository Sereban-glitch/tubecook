"""Караоке-ряды v4.1: сброс по предложениям/паузам, отсутствие переносов
libass (а значит и наложений букв), motion-слои (прогресс, кинетика, бейджи)."""
import re
from pathlib import Path

import pytest

from tubecook.media.ass import (MAX_ROW_PX, PAUSE_SPLIT_S, _Measurer,
                                _pack_rows, _row_width_px, _sentence_ids,
                                build_ass)
from tubecook.media.scenes import (Scene, sentence_word_spans, split_sentences)

from conftest import words_of

BOLDFONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

SCRIPT2 = ("Первая фраза говорит про суд и Водоканал в Запорожье. "
           "Вторая фраза называет номер дела 280/8165/23 и суд.")


def _dial(text: str, layer: str = "0") -> list:
    pat = (r"Dialogue: %s,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),(\w+)"
           r",,0,0,0,,(.*)$" % layer)
    out = []
    for m in re.finditer(pat, text, re.M):
        out.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return out


def _sec(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


# ---------------------------------------------------- сброс строк по границам

def test_rows_never_mix_sentences():
    """Слова двух предложений НИКОГДА не в одном ряду (склейка устранена)."""
    words = words_of(SCRIPT2)
    spans = sentence_word_spans(SCRIPT2, words)
    ids = _sentence_ids(words, spans)
    measurer = _Measurer(BOLDFONT, 64)
    rows = _pack_rows(words, measurer, ids)
    assert len(rows) >= 2
    for row in rows:
        row_ids = {ids[i] for i in range(len(words)) if words[i] in row}
        # точнее: по индексам
        first = next(i for i, w in enumerate(words) if w is row[0])
        row_ids = {ids[first + k] for k in range(len(row))}
        assert len(row_ids) == 1, "ряд склеил границу предложений"


def test_rows_reset_on_pause():
    """Пауза между словами >= PAUSE_SPLIT_S сбрасывает строку даже внутри
    предложения (диктор делает смысловую паузу — строка тоже сбрасывается)."""
    words = [
        {"word": "первое", "start": 0.0, "end": 0.3},
        {"word": "слово", "start": 0.32, "end": 0.6},
        {"word": "после", "start": 0.6 + PAUSE_SPLIT_S + 0.05, "end": 1.6},
        {"word": "паузы", "start": 1.65, "end": 2.0},
    ]
    ids = _sentence_ids(words, None)
    measurer = _Measurer(BOLDFONT, 64)
    rows = _pack_rows(words, measurer, ids, pause_s=PAUSE_SPLIT_S)
    assert len(rows) == 2                       # сброс по паузе
    assert [w["word"] for w in rows[0]] == ["первое", "слово"]
    assert [w["word"] for w in rows[1]] == ["после", "паузы"]


def test_rows_fit_width_no_libass_wrap():
    """Каждый ряд уже 940 px — libass не переносит -> вертикальных наложений
    букв при переносе нет по построению."""
    long_words = words_of(
        "Коммунальное предприятие требовало оплату начислений и долгов "
        "а жители общины обратились в суд с иском оспорить требования")
    ids = _sentence_ids(long_words, None)
    measurer = _Measurer(BOLDFONT, 64)
    assert measurer.ok, "в среде тестов должен быть DejaVu Bold"
    rows = _pack_rows(long_words, measurer, ids)
    for row in rows:
        assert len(row) <= 4
        assert _row_width_px(row, measurer) <= MAX_ROW_PX


def test_ass_rows_sequential_with_sentence_spans(tmp_path):
    """События-ряды последовательны (без наложений) и покрывают речь."""
    words = words_of(SCRIPT2)
    spans = sentence_word_spans(SCRIPT2, words)
    ass = build_ass(words, "хук", tmp_path / "s.ass", sentence_spans=spans)
    ev = _dial(ass.read_text(encoding="utf-8"))
    assert ev
    starts = [_sec(s) for s, _, _, _ in ev]
    ends = [_sec(e) for _, e, _, _ in ev]
    for i in range(1, len(ev)):
        assert starts[i] >= ends[i - 1] - 0.03
    assert max(ends) >= words[-1]["end"] - 0.05
    # каждый ряд привязан к фиксированной позиции (нет авто-переноса)
    for _, _, _, txt in ev:
        assert "\\pos(540," in txt and "\\an5" in txt


# ------------------------------------------------------- полоска прогресса

def test_progress_bar_events(tmp_path):
    """Тонкая полоска: трек на всю длительность + монотонный fill до конца."""
    words = words_of("Короткий тест прогресса бара")
    total = 10.0
    ass = build_ass(words, "", tmp_path / "s.ass", total=total)
    body = ass.read_text(encoding="utf-8")
    ev = _dial(body, layer="4")
    styles = {s for _, _, s, _ in ev}
    assert "ProgressTrack" in styles and "ProgressFill" in styles

    fills = [x for x in ev if x[2] == "ProgressFill"]
    assert fills
    # непрерывное покрытие 0..total
    assert abs(_sec(fills[0][0])) < 0.01
    assert abs(_sec(fills[-1][1]) - total) < 0.01
    for i in range(1, len(fills)):
        assert _sec(fills[i][0]) >= _sec(fills[i - 1][1]) - 0.01
    # ширины монотонно растут и доходят до полного спана
    widths = [int(m.group(1)) for _, _, _, t in fills
              for m in [re.search(r"l (\d+) 0", t)] if m]
    assert widths == sorted(widths)
    assert widths[-1] >= 900 - 5


# ----------------------------------------------------- кинетика и бейджи

def _scene(i, kind, start, end, badge="", kinetic=""):
    return Scene(index=i, kind=kind, text="т", start=start, end=end,
                 badge=badge, kinetic=kinetic)


def test_kinetic_case_number_pop(tmp_path):
    """Номер дела — кинетика: pop scale-up с overshoot (\\t + \\fscx108)."""
    words = words_of("Тест кинетики")
    scenes = [_scene(0, "case", 0.0, 5.0, badge="ДЕЛО № 280/8165/23",
                     kinetic="ДЕЛО № 280/8165/23")]
    ass = build_ass(words, "", tmp_path / "s.ass", scenes=scenes, total=6.0)
    body = ass.read_text(encoding="utf-8")
    ev = _dial(body, layer="3")
    kin = [x for x in ev if x[2] == "Kinetic"]
    assert len(kin) == 1
    _, e, _, txt = kin[0]
    assert "280/8165/23" in txt
    assert "\\t(0,200,\\fscx108\\fscy108)" in txt     # overshoot
    assert "\\fscx78\\fscy78" in txt                  # старт от 78%
    # окно внутри сцены
    assert _sec(e) <= 5.0 - 0.24


def test_badges_slide_in(tmp_path):
    """Плашки-бейджи: плавный въезд (\\move) + scale-settle, по одной на сцену."""
    words = words_of("Тест бейджей")
    scenes = [
        _scene(0, "verdict", 0.0, 4.0, badge="РЕШЕНИЕ СУДА"),
        _scene(1, "problem", 4.0, 8.0, badge="СТОРОНЫ СПОРА"),
        _scene(2, "fact", 8.0, 12.0, badge="ФАКТ 1"),
    ]
    ass = build_ass(words, "", tmp_path / "s.ass", scenes=scenes, total=12.0)
    body = ass.read_text(encoding="utf-8")
    ev = [x for x in _dial(body, layer="3") if x[2] == "Badge"]
    assert len(ev) == 3
    texts = " | ".join(t for *_, t in ev)
    assert "РЕШЕНИЕ СУДА" in texts
    assert "СТОРОНЫ СПОРА" in texts
    assert "ФАКТ 1" in texts
    for s, e, _, t in ev:
        assert "\\move(" in t and "\\t(0,300,\\fscx100\\fscy100)" in t
        # соседние окна бейджей не пересекаются
    starts = sorted(_sec(s) for s, _, _, _ in ev)
    ends = sorted(_sec(e) for _, e, _, _ in ev)
    for i in range(1, len(starts)):
        assert starts[i] >= ends[i - 1] - 0.01


def test_kinetic_priority_over_badge(tmp_path):
    """Если у сцены есть кинетический акцент — бейдж не дублируется."""
    words = words_of("Приоритет")
    scenes = [_scene(0, "case", 0.0, 5.0, badge="ДЕЛО № 1/2/23",
                     kinetic="ДЕЛО № 1/2/23")]
    ass = build_ass(words, "", tmp_path / "s.ass", scenes=scenes, total=6.0)
    body = ass.read_text(encoding="utf-8")
    ev = _dial(body, layer="3")
    assert len(ev) == 1
    assert ev[0][2] == "Kinetic"


def test_no_overlay_for_hook_and_outro(tmp_path):
    """hook/outro не получают бейджей (у них свои фирменные карточки)."""
    words = words_of("Хук и аутро")
    scenes = [_scene(0, "hook", 0.0, 4.0), _scene(1, "outro", 4.0, 8.0)]
    ass = build_ass(words, "", tmp_path / "s.ass", scenes=scenes, total=8.0)
    body = ass.read_text(encoding="utf-8")
    assert not _dial(body, layer="3")
