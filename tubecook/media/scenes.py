"""Раскладка сценария на осмысленные сцены + выравнивание по таймингам слов.

Сцена != слайд: каждая привязана к своей фразе озвучки (WordBoundary),
вид (hook/fact/stat/compare/quote/outro) выбирается по смыслу фразы,
visual_plan из задания может переопределить вид явно. Длительности берутся
из ФАКТИЧЕСКИХ таймингов речи, а не из числа слов (ТЗ).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Scene:
    index: int
    kind: str                 # hook | fact | stat | compare | quote | outro
    text: str
    start: float              # c, по словам озвучки
    end: float
    dur: float = 0.0
    number: str = ""
    a: str = ""
    b: str = ""
    attribution: str = ""
    note: str = ""
    channel: str = "Свободные люди Запорожья"
    demo: bool = False
    seed: int = 42
    out_dir: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_NUM_RE = re.compile(r"[\$€]?\d[\d\s.,]*\d?%?(?:[×x]\d+)?|[\$€]\d+")
_COMPARE_RE = re.compile(r"\b(vs|versus|сравн\w*|вместо|отлич\w*|против)\b", re.I)


def split_sentences(script: str) -> list:
    sents = [s.strip() for s in _SENT_SPLIT.split(script.strip()) if s.strip()]
    return sents


def _norm(tok: str) -> str:
    return re.sub(r"[^\wа-яё]", "", tok.lower())


def _classify(sent: str, idx: int, total: int, plan: list) -> str:
    """Выбор вида сцены по смыслу фразы; visual_plan может переопределить."""
    if idx == 0:
        return "hook"
    if idx == total - 1:
        return "outro"
    # явный override из visual_plan: строки вида "stat: ...", "compare: ...",
    # "quote: ..." относятся к n-й не-хук/не-аутро фразе по порядку
    body_i = idx - 1
    if plan and body_i < len(plan):
        hint = str(plan[body_i]).lower()
        for kind in ("stat", "compare", "quote", "fact"):
            if hint.startswith(kind):
                return kind
    if _COMPARE_RE.search(sent):
        return "compare"
    if sent.endswith("?"):
        return "quote"
    if _NUM_RE.search(sent):
        return "stat"
    return "fact"


def _extract_number(sent: str) -> str:
    m = _NUM_RE.search(sent)
    return m.group(0).strip() if m else ""


def _split_compare(sent: str) -> tuple:
    m = _COMPARE_RE.search(sent)
    if not m:
        return sent, ""
    a = sent[:m.start()].strip(" ,—-")
    b = sent[m.end():].strip(" ,—-")
    return a or sent, b


def align_words_to_sentences(words: list, sentences: list) -> list:
    """Каждому предложению — диапазон индексов слов [i, j) по нормализованным токенам."""
    ranges = []
    i = 0
    for sent in sentences:
        toks = [_norm(t) for t in sent.split() if _norm(t)]
        # пропускаем слова, пока не найдём начало предложения
        while i < len(words) and toks and _norm(words[i]["word"]) != toks[0]:
            i += 1
        start_i = i
        j = 0
        while i < len(words) and j < len(toks):
            if _norm(words[i]["word"]) == toks[j]:
                j += 1
            i += 1
        ranges.append((start_i, max(start_i + 1, i)))
    return ranges


def build_scenes(payload: dict, words: list, speech_end: float,
                 plan: list | None = None, channel: str = "Свободные люди Запорожья",
                 out_dir: str = "") -> list:
    """payload + слова озвучки -> список Scene с длительностями по факту речи."""
    script = payload.get("script", "")
    sentences = split_sentences(script)
    if not sentences:
        raise ValueError("пустой сценарий")
    plan = plan if plan is not None else payload.get("visual_plan", [])
    demo = bool(payload.get("demo"))
    ranges = align_words_to_sentences(words, sentences)

    scenes: list = []
    fact_idx = 0
    facts = payload.get("facts", [])
    for idx, sent in enumerate(sentences):
        kind = _classify(sent, idx, len(sentences), plan)
        i, j = ranges[idx]
        start = words[i]["start"] if i < len(words) else 0.0
        end = words[j - 1]["end"] if j - 1 < len(words) else speech_end
        sc = Scene(
            index=idx, kind=kind, text=sent,
            start=max(0.0, start - 0.15), end=min(speech_end + 0.05, end + 0.2),
            demo=demo, out_dir=out_dir, seed=100 + idx * 13,
            channel=channel)
        if kind == "hook":
            src = payload.get("sources", [])
            sc.note = _domain_of(src[0]["url"]) if src else ""
        elif kind == "stat":
            sc.number = _extract_number(sent)
        elif kind == "compare":
            sc.a, sc.b = _split_compare(sent)
        elif kind == "fact":
            fact_idx += 1
            sc.index_display = fact_idx
            if fact_idx - 1 < len(facts):
                sc.attribution = facts[fact_idx - 1].get("attribution", "")
        scenes.append(sc)

    scenes = _balance_durations(scenes, speech_end)
    return scenes


def _balance_durations(scenes: list, speech_end: float, min_dur: float = 2.2) -> list:
    """Длительности: покрыть речь, минимум 2.2 c на сцену, без дыр."""
    for sc in scenes:
        sc.dur = max(min_dur, sc.end - sc.start)
    total = sum(sc.dur for sc in scenes)
    # сцены должны суммарно >= speech_end (xfade съест overlap, компенсируем с запасом)
    need = speech_end + 0.4
    if total < need:
        add = (need - total) / len(scenes)
        for sc in scenes:
            sc.dur += add
        total = need
    # чуть растягиваем финальную сцену: законченная мысль + визуальная точка
    scenes[-1].dur += 0.35
    return scenes


def _domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else ""
