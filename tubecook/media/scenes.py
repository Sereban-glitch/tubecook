"""Раскладка сценария на осмысленные сцены + выравнивание по таймингам слов.

Сцена != слайд: каждая привязана к своей фразе озвучки (WordBoundary),
вид (hook/fact/stat/compare/quote/outro) выбирается по смыслу фразы,
visual_plan из задания может переопределить вид явно. Длительности берутся
из ФАКТИЧЕСКИХ таймингов речи, а не из числа слов (ТЗ).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Scene:
    index: int
    kind: str                 # hook | fact | stat | compare | quote | outro
                              # | case | verdict | problem | practical_value
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
    # --- motion design / юридические карточки ---
    badge: str = ""            # текст плашки-бейджа (ASS-анимация въезда)
    kinetic: str = ""          # крупный кинетический акцент (номер дела, цифра)
    case_number: str = ""      # «280/8165/23»
    points: list = field(default_factory=list)   # пункты карточки (из описания)
    subtitle: str = ""         # подпись карточки дела (название суда и т.п.)
    image: str = ""            # абсолютный путь к фото сцены, если есть

    def to_dict(self) -> dict:
        return dict(self.__dict__)


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_NUM_RE = re.compile(r"[\$€]?\d[\d\s.,]*\d?%?(?:[×x]\d+)?|[\$€]\d+")
_COMPARE_RE = re.compile(r"\b(vs|versus|сравн[\wа-яё]*|вместо|отлич[\wа-яё]*|против)\b", re.I)
_CASE_RE = re.compile(r"\b(\d{1,6}/\d{1,8}/\d{2,4})\b")

# виды сцен, которые plan может задать явно (dict {"kind": ...})
_PLAN_KINDS = ("hook", "outro", "stat", "compare", "quote", "fact",
              "case", "verdict", "problem", "practical_value")

# надписи-бейджи по виду сцены (плавный въезд плашки сверху)
_KIND_BADGES = {
    "verdict": "РЕШЕНИЕ СУДА",
    "problem": "СТОРОНЫ СПОРА",
    "practical_value": "ПРАКТИЧЕСКИЙ ВЫВОД",
    "compare": "СРАВНЕНИЕ",
    "quote": "ЦИТАТА",
    "fact": "ФАКТ",
}


def split_sentences(script: str) -> list:
    sents = [s.strip() for s in _SENT_SPLIT.split(script.strip()) if s.strip()]
    return sents


def sentence_word_spans(script: str, words: list) -> list:
    """Диапазоны слов [i, j) по предложениям — для субтитров и сцен.

    Единая точка выравнивания: и ass.py, и build_scenes используют одни
    и те же границы предложений (строка субтитров никогда не склеивает
    конец одного предложения с началом следующего).
    """
    return align_words_to_sentences(words, split_sentences(script))


def extract_case_number(text: str) -> str:
    """Номер судебного дела в украинском формате «280/8165/23» (если есть)."""
    m = _CASE_RE.search(text or "")
    return m.group(1) if m else ""


def parse_plan_description(desc: str) -> tuple:
    """Описание плана -> (метка-префикс, [пункты]).

    «Решение суда: действия… • обязать…» -> ("Решение суда",
        ["действия…", "обязать…"]). Пункты после префикса не теряются.
    """
    desc = (desc or "").strip()
    if not desc:
        return "", []
    label = ""
    m = re.match(r"^([^:•]{1,40}):\s*(.*)$", desc, re.S)
    if m:
        label = m.group(1).strip()
        desc = m.group(2).strip()
    points = [p.strip() for p in desc.split("•") if p.strip()]
    return label, points


def _norm(tok: str) -> str:
    return re.sub(r"[^\wа-яё]", "", tok.lower())


def _plan_item(plan: list, idx: int):
    """Элемент visual_plan для предложения idx (или None).

    Поддерживает обе конвенции планов:
    - план индексирован ПО СЦЕНАМ (первый элемент dict с kind="hook",
      как в job_domdara_vodokanal.json): item = plan[idx];
    - план перечисляет только body-фразы (SAMPLE: ["stat: 42"]):
      item = plan[idx-1] (поведение rc1 сохранено).
    """
    if not plan:
        return None
    hook_indexed = (isinstance(plan[0], dict) and
                    str(plan[0].get("kind", "")).lower() == "hook")
    if hook_indexed:
        return plan[idx] if 0 <= idx < len(plan) else None
    body_i = idx - 1
    return plan[body_i] if 0 <= body_i < len(plan) else None


def _classify(sent: str, idx: int, total: int, plan: list) -> str:
    """Выбор вида сцены по смыслу фразы; visual_plan может переопределить."""
    if idx == 0:
        return "hook"
    if idx == total - 1:
        return "outro"
    # явный override из visual_plan (см. _plan_item — обе конвенции планов)
    item = _plan_item(plan, idx)
    if item is not None:
        if isinstance(item, dict):
            k = str(item.get("kind", "")).lower()
            if k == "fact_card":
                k = "case"          # карточка дела — юридический шаблон
            if k in _PLAN_KINDS:
                # защита: hook/outro в теле плана — признак кривого плана,
                # не ломаем раскладку сцен
                if k == "hook" and idx != 0:
                    k = ""
                elif k == "outro" and idx != total - 1:
                    k = ""
                if k:
                    return k
            if "fact" in k:
                return "fact"
        else:
            hint = str(item).lower()
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


def _subtoks(word_str: str) -> list[str]:
    return [_norm(t) for t in re.findall(r"[\wа-яё]+", str(word_str).lower()) if _norm(t)]


def align_words_to_sentences(words: list, sentences: list) -> list:
    """Каждому предложению — диапазон индексов слов [i, j) по нормализованным токенам."""
    if not sentences:
        return []
    if not words:
        return [(0, 0) for _ in sentences]

    n_sents = len(sentences)
    n_words = len(words)

    sent_tokens = []
    for s in sentences:
        toks = [_norm(t) for t in re.findall(r"[\wа-яё]+", s.lower()) if _norm(t)]
        sent_tokens.append(toks)

    word_subtoks = [_subtoks(w.get("word", "")) for w in words]

    starts = [0]
    cur_w = 0
    for s_idx in range(1, n_sents):
        target_toks = sent_tokens[s_idx]
        if not target_toks:
            starts.append(min(cur_w, n_words))
            continue

        first_tok = target_toks[0]
        second_tok = target_toks[1] if len(target_toks) > 1 else None

        found_idx = None
        for w_i in range(cur_w + 1, n_words):
            sub = word_subtoks[w_i]
            if first_tok in sub:
                if second_tok and w_i + 1 < n_words:
                    next_sub = word_subtoks[w_i + 1]
                    if second_tok in sub or second_tok in next_sub:
                        found_idx = w_i
                        break
                else:
                    found_idx = w_i
                    break

        if found_idx is None:
            rem_sents = n_sents - s_idx
            rem_words = n_words - cur_w
            step = max(1, rem_words // (rem_sents + 1))
            found_idx = min(cur_w + step, n_words - rem_sents)

        starts.append(found_idx)
        cur_w = found_idx

    ranges = []
    for s_idx in range(n_sents):
        a = starts[s_idx]
        b = starts[s_idx + 1] if s_idx + 1 < n_sents else n_words
        b = max(a + 1, b)
        ranges.append((a, b))

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
    meta_case = str((payload.get("meta") or {}).get("primary_case_number", ""))

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

        # описание/фото из visual_plan (если задано) — данные для карточек
        desc, image_url = "", ""
        item = _plan_item(plan, idx)
        if item is not None and isinstance(item, dict):
            desc = str(item.get("description", "") or "")
            image_url = str(item.get("image_url", "") or "")
        label, points = parse_plan_description(desc)

        # номер дела: описание -> текст фразы -> meta задания
        sc.case_number = (extract_case_number(desc) or
                          extract_case_number(sent) or
                          extract_case_number(meta_case) or "")

        if kind == "hook":
            src = payload.get("sources", [])
            sc.note = _domain_of(src[0]["url"]) if src else ""
        elif kind == "stat":
            sc.number = _extract_number(sent)
            sc.badge = "ДАННЫЕ"
            sc.kinetic = sc.number        # крупный кинетический акцент
        elif kind == "compare":
            sc.a, sc.b = _split_compare(sent)
            sc.badge = _KIND_BADGES["compare"]
        elif kind == "quote":
            sc.badge = _KIND_BADGES["quote"]
        elif kind == "case":
            sc.badge = f"ДЕЛО № {sc.case_number}" if sc.case_number else "КАРТОЧКА ДЕЛА"
            sc.kinetic = sc.badge          # scale-up акцент на номере дела
            sc.points = points[:4]
            # подпись карточки: название суда и т.п. (последний пункт описания)
            sc.subtitle = points[-1] if len(points) >= 2 else (points[0] if points else "")
        elif kind == "verdict":
            sc.badge = _KIND_BADGES["verdict"]
            sc.points = points[:5]
        elif kind == "problem":
            sc.badge = _KIND_BADGES["problem"]
            sc.points = points[:4]
        elif kind == "practical_value":
            sc.badge = _KIND_BADGES["practical_value"]
            sc.points = points[:5]
        elif kind == "fact":
            fact_idx += 1
            sc.index_display = fact_idx
            sc.badge = f"ФАКТ {fact_idx}"
            if fact_idx - 1 < len(facts):
                sc.attribution = facts[fact_idx - 1].get("attribution", "")

        # фото сцены (если указано и файл реально существует на диске)
        if image_url:
            p = Path(image_url)
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            sc.image = str(p) if p.exists() else ""
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
