"""Караоке-субтитры: длительности, покрытие, экранирование, читаемость."""
import re

from tubecook.media.ass import _chunk_words, build_ass

from conftest import words_of

SCRIPT = ("Первое предложение для проверки субтитров. "
          "Второе с цифрой 42 для статистики. "
          "Третье завершает мысль?")


def test_chunk_words_limits():
    words = words_of(SCRIPT * 3)
    for line in _chunk_words(words):
        assert len(line) <= 4
        assert line[-1]["end"] - line[0]["start"] <= 2.4 + 0.01


def test_ass_lines_cover_speech(tmp_path):
    words = words_of(SCRIPT)
    ass = build_ass(words, "Хук для теста", tmp_path / "subs.ass")
    text = ass.read_text(encoding="utf-8")
    dialogues = re.findall(
        r"Dialogue: 0,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),Karaoke", text)
    assert dialogues
    starts, ends = [], []
    for s, e in dialogues:
        starts.append(_sec(s))
        ends.append(_sec(e))
        assert _sec(e) > _sec(s)
    # без наложений
    for i in range(1, len(starts)):
        assert starts[i] >= ends[i - 1] - 0.03
    # покрытие: последний конец >= конца речи
    voice_end = words[-1]["end"]
    assert max(ends) >= voice_end - 0.05


def test_ass_karaoke_durations_match_words(tmp_path):
    words = words_of("слово одно другое")
    ass = build_ass(words, "", tmp_path / "subs.ass")
    body = ass.read_text(encoding="utf-8")
    m = re.search(r"Karaoke.*?,,\{\\fad\(100,100\)\}(.*?)$", body, re.M)
    line = m.group(1)
    ks = [int(k) for k in re.findall(r"\{\\k(\d+)\}", line)]
    # сумма \k (в сотых секундах) примерно равна окну строки
    dlg = re.search(r"Dialogue: 0,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),Karaoke",
                    body)
    window_cs = (_sec(dlg.group(2)) - _sec(dlg.group(1))) * 100
    # \k покрывает слова+паузы; хвост строки (~0.28 c) остаётся без подсветки
    assert abs(sum(ks) - window_cs) <= 35


def test_ass_escapes_braces(tmp_path):
    words = [{"word": "скобки {и}", "start": 0.1, "end": 0.4},
             {"word": "текст", "start": 0.5, "end": 0.8}]
    ass = build_ass(words, "", tmp_path / "subs.ass")
    body = ass.read_text(encoding="utf-8")
    assert "{и}" not in re.sub(r"\{\\\\?[a-zA-Z]+\d*\}", "", body)


def test_ass_style_mobile_readable(tmp_path):
    words = words_of("проверка стиля")
    ass = build_ass(words, "х", tmp_path / "s.ass")
    body = ass.read_text(encoding="utf-8")
    style = re.search(r"Style: Karaoke,(.*)", body).group(1)
    fields = [f.strip() for f in style.split(",")]
    # Format: Name,Fontname,Fontsize,Prim,Sec,Out,Back,Bold,Ital,Und,Str,ScaleX,
    # ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Align,ML,MR,MarginV,Enc
    assert fields[1] == "64"          # крупный жирный шрифт
    assert fields[15] == "5"           # плотная обводка
    assert fields[20] == "430"         # MarginV: над UI плеера
    assert "PlayResX: 1080" in body and "PlayResY: 1920" in body


def _sec(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
