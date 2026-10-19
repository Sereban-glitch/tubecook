"""Сцены: раскладка сценария, классификация, длительности по речи."""
from tubecook.media.scenes import (align_words_to_sentences, build_scenes,
                                   split_sentences)

from conftest import SAMPLE, words_of
from tubecook.protocol import parse_message

SCRIPT = ("Хук первого предложения достаточно длинный. "
          "Второе предложение содержит цифру 42 для сцены. "
          "Третье сравнивает локальные модели vs облачные. "
          "Четвёртое задаёт вопрос аудитории? "
          "Финальное завершает мысль полностью.")


def test_split_sentences():
    sents = split_sentences(SCRIPT)
    assert len(sents) == 5
    assert sents[-1].startswith("Финальное")


def test_align_words_covers_all():
    words = words_of(SCRIPT)
    sents = split_sentences(SCRIPT)
    ranges = align_words_to_sentences(words, sents)
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(words)
    for (a, b) in ranges:
        assert b > a


def test_build_scenes_kinds_and_durations():
    words = words_of(SCRIPT)
    payload = {"script": SCRIPT, "visual_plan": [], "facts": [
        {"text": "факт", "attribution": "ист"}]}
    scenes = build_scenes(payload, words, words[-1]["end"], out_dir="/tmp/na")
    assert scenes[0].kind == "hook"
    assert scenes[-1].kind == "outro"
    kinds = [s.kind for s in scenes]
    assert "stat" in kinds and "compare" in kinds and "quote" in kinds
    # длительности: минимум 2.2 с и суммарно >= конец речи
    for s in scenes:
        assert s.dur >= 2.2
    assert sum(s.dur for s in scenes) >= words[-1]["end"]


def test_visual_plan_override():
    words = words_of(SCRIPT)
    payload = {"script": SCRIPT, "facts": [{"text": "ф", "attribution": "и"}],
               "visual_plan": ["quote: явно", "stat: явно", "fact: явно"]}
    scenes = build_scenes(payload, words, words[-1]["end"], out_dir="/tmp/na")
    assert scenes[1].kind == "quote"
    assert scenes[2].kind == "stat"
    assert scenes[3].kind == "fact"


def test_demo_flag_propagates():
    words = words_of(SCRIPT)
    payload = {"script": SCRIPT, "demo": True, "facts": []}
    scenes = build_scenes(payload, words, words[-1]["end"], out_dir="/tmp/na")
    assert all(s.demo for s in scenes)


def test_real_sample_payload():
    parsed = parse_message(SAMPLE)
    script = parsed.job["script"]
    words = words_of(script)
    scenes = build_scenes(parsed.job, words, words[-1]["end"], out_dir="/tmp/na")
    assert len(scenes) == len(split_sentences(script))
