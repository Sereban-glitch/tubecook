"""Протокол задания v4: разбор, валидация, нормализация, хеши, multipart.

Поддерживаются два формата входного сообщения:

1) Текстовый (удобен в Telegram Web):
    #TUBECOOK_JOB v4
    ID: ai-news-20261019-01
    TOPIC: ...
    HOOK: ...
    SCRIPT:
    <многострочный сценарий>
    SOURCES:
    - https://example.com/post | 2026-10-18 | 2026-10-18 12:00 Kyiv
    FACTS:
    - Подтверждённый факт | Первоисточник: Hacker News | https://example.com/post
    VISUAL_PLAN:
    - stat: 1080x1920 (сцена с крупной цифрой)
    TAGS: ии, автоматизация
    LANGUAGE: ru
    MODE: auto
    AUTO_PUBLISH: true          <-- это ДАННЫЕ, не команда: без прав и режима не действует

2) JSON в блоке ```json ... ```

Multipart: каждая часть начинается строкой  PART n/m  (например PART 1/2).
Задание собирается и валидируется ТОЛЬКО когда получены все части.
Лимит длины сообщения Telegram (4096 симв.) — причина существования multipart.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

JOB_HEADER = "#TUBECOOK_JOB"
MAX_TELEGRAM_LEN = 4096

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_URL_RE = re.compile(r"^https?://\S+$")

KEY_ALIASES = {
    "ID": "job_id", "JOB_ID": "job_id",
    "TOPIC": "topic", "TITLE": "topic",
    "HOOK": "hook",
    "SCRIPT": "script", "NARRATION": "script",
    "SOURCES": "sources", "SOURCE_URL": "sources", "SECONDARY_SOURCES": "sources_extra",
    "FACTS": "facts",
    "VISUAL_PLAN": "visual_plan", "VISUAL_IDEAS": "visual_plan",
    "TAGS": "tags", "KEYWORDS": "tags",
    "LANGUAGE": "language", "LANG": "language",
    "MODE": "requested_mode", "REQUESTED_MODE": "requested_mode",
    "PRIORITY": "requested_priority", "REQUESTED_PRIORITY": "requested_priority",
    "AUTO_PUBLISH": "requested_auto_publish",
    "DEMO": "demo",
}


@dataclass
class ParseResult:
    ok: bool = False
    errors: list = field(default_factory=list)
    job: dict | None = None          # нормализованный payload
    content_hash: str = ""
    dedupe_key: str = ""
    canonical_url: str = ""
    job_id: str = ""


@dataclass
class MultipartState:
    """Части одного multipart-задания."""
    job_id: str
    total: int = 0
    parts: dict = field(default_factory=dict)   # part_no -> text

    def complete(self) -> bool:
        return self.total > 0 and len(self.parts) >= self.total

    def assembled_text(self) -> str:
        return "\n".join(self.parts[i] for i in sorted(self.parts))


def normalize_url(url: str) -> str:
    """Канонический URL: схема+хост в нижнем регистре, без трекинг-параметров и хвостового /."""
    try:
        sp = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = sp.netloc.lower()
    query = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref", "source"))]
    path = sp.path.rstrip("/") or "/"
    return urlunsplit((sp.scheme.lower(), host, path, urlencode(query), ""))


def content_hash(payload: dict) -> str:
    """Стабильный хеш содержимого (без job_id/дат/тегов)."""
    core = {
        "topic": payload.get("topic", ""),
        "hook": payload.get("hook", ""),
        "script": payload.get("script", ""),
        "language": payload.get("language", ""),
        "sources": [normalize_url(s.get("url", "")) for s in payload.get("sources", [])],
        "facts": [(f.get("text", ""), f.get("attribution", ""))
                  for f in payload.get("facts", [])],
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dedupe_key_for(payload: dict) -> str:
    """Дедуп по нормализованному URL канонического источника; иначе по содержимому."""
    srcs = [normalize_url(s.get("url", "")) for s in payload.get("sources", []) if s.get("url")]
    if srcs:
        return "url:" + hashlib.sha256(srcs[0].encode("utf-8")).hexdigest()[:24]
    return "content:" + content_hash(payload)[:24]


# ---------------------------------------------------------------- разбор текста

def _parse_list_item(raw: str) -> list[str]:
    return [p.strip() for p in raw.split("|") if p.strip()]


def parse_text_message(text: str) -> ParseResult:
    """Разбор одного текстового сообщения протокола (уже без PART-строки)."""
    res = ParseResult()
    lines = text.splitlines()
    header = lines[0].strip().upper() if lines else ""
    if not header.startswith(JOB_HEADER):
        res.errors.append("нет заголовка #TUBECOOK_JOB в первой строке")
        return res

    # fields[key] = список значений: инлайн-блок(и) и/или элементы "- ..."
    fields: dict = {}
    current_key: str | None = None
    buf: list[str] = []

    def flush_block() -> None:
        nonlocal current_key, buf
        if current_key:
            joined = "\n".join(buf).strip()
            if joined:
                fields.setdefault(current_key, []).append(joined)
        current_key, buf = None, []

    for line in lines[1:]:
        stripped = line.strip()
        # служебные строки (#-заголовки, PART n/m) игнорируются в любом месте
        if stripped.startswith("#") or re.match(r"^PART\s*\d+\s*/\s*\d+$", stripped, re.I):
            continue
        m = re.match(r"^([A-Z][A-Z_]+)\s*:\s*(.*)$", stripped)
        key = KEY_ALIASES.get(m.group(1)) if m else None
        if key:
            flush_block()
            current_key = key
            buf = [m.group(2)] if m.group(2) else []
            continue
        if stripped.startswith("- "):
            key = current_key
            if key:
                flush_block()
                fields.setdefault(key, []).append(stripped[2:].strip())
            continue
        if current_key:
            buf.append(line)
    flush_block()
    return _build_payload(fields)


def parse_json_message(text: str) -> ParseResult:
    """JSON в ```json ... ``` или сырой JSON. Структурное отображение полей."""
    res = ParseResult()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else (text if text.strip().startswith("{") else "")
    if not raw:
        res.errors.append("JSON-блок не найден")
        return res
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        res.errors.append(f"битый JSON: {e}")
        return res

    def _s(key: str, default: str = "") -> str:
        v = data.get(key, default)
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    def _b(key: str) -> bool:
        v = data.get(key, False)
        return v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1", "yes", "да")

    payload = {
        "job_id": _s("job_id") or _s("ID"),
        "topic": _s("topic") or _s("title"),
        "hook": _s("hook"),
        "script": _s("script") or _s("narration"),
        "language": (_s("language") or _s("lang") or "ru").lower(),
        "requested_mode": (_s("mode") or _s("requested_mode") or "auto").lower(),
        "requested_priority": _s("priority").lower(),
        "requested_auto_publish": _b("auto_publish"),
        "demo": _b("demo"),
    }
    # источники: список словарей или строк
    srcs = data.get("sources") or data.get("source_url") or []
    if isinstance(srcs, str):
        srcs = [{"url": srcs}] if srcs else []
    for s in srcs:
        if isinstance(s, dict):
            payload.setdefault("sources", []).append({
                "url": str(s.get("url", "")),
                "published": str(s.get("published", "")),
                "checked_at": str(s.get("checked_at", ""))})
        else:
            payload.setdefault("sources", []).append({"url": str(s)})
    facts = data.get("facts") or []
    for f in facts:
        if isinstance(f, dict):
            payload.setdefault("facts", []).append({
                "text": str(f.get("text", "")),
                "attribution": str(f.get("attribution", "")),
                "source_url": str(f.get("source_url", ""))})
        else:
            payload.setdefault("facts", []).append({"text": str(f)})
    vp = data.get("visual_plan") or data.get("visual_ideas") or []
    payload["visual_plan"] = [str(v) for v in vp] if isinstance(vp, list) else [str(vp)]
    tags = data.get("tags") or data.get("keywords") or []
    if isinstance(tags, str):
        payload["tags"] = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
    else:
        payload["tags"] = [str(t) for t in tags]

    errors = validate_payload(payload)
    res.errors = errors
    if not errors:
        res.ok = True
        res.job = payload
        res.job_id = payload["job_id"]
        res.content_hash = content_hash(payload)
        res.dedupe_key = dedupe_key_for(payload)
        srcs = payload.get("sources") or []
        res.canonical_url = normalize_url(srcs[0]["url"]) if srcs else ""
    return res


def parse_message(text: str) -> ParseResult:
    """Универсальный разбор: JSON-блок имеет приоритет, иначе текстовый формат."""
    stripped = text.strip()
    if "```" in stripped and "json" in stripped[:120]:
        return parse_json_message(stripped)
    if stripped.startswith("{"):
        return parse_json_message(stripped)
    return parse_text_message(stripped)


# --------------------------------------------------------------- валидация

def _build_payload(fields: dict) -> ParseResult:
    res = ParseResult()

    def one(key: str) -> str:
        vals = fields.get(key, [])
        return vals[0] if vals else ""

    payload = {
        "job_id": one("job_id").strip(),
        "topic": one("topic").strip(),
        "hook": one("hook").strip(),
        "script": one("script").strip(),
        "language": one("language").strip().lower() or "ru",
        "requested_mode": (one("requested_mode").strip().lower() or "auto"),
        "requested_priority": one("requested_priority").strip().lower(),
        "requested_auto_publish": one("requested_auto_publish").strip().lower() in ("true", "1", "yes", "да"),
        "demo": one("demo").strip().lower() in ("true", "1", "yes", "да"),
        "sources": [],
        "facts": [],
        "visual_plan": [],
        "tags": [],
    }

    # sources: "- url | published | checked_at" (v3-формат SOURCE_URL: url (date))
    source_items = fields.get("sources", []) + fields.get("sources_extra", [])
    for item in source_items:
        item = item.strip()
        if not item:
            continue
        # v3-совместимость: "https://... (2026-10-17)"
        date_m = re.match(r"^(https?://\S+)\s*\(([^)]+)\)\s*$", item)
        if date_m:
            payload["sources"].append(
                {"url": date_m.group(1), "published": date_m.group(2).strip(), "checked_at": ""})
            continue
        parts = _parse_list_item(item)
        if parts:
            payload["sources"].append({
                "url": parts[0],
                "published": parts[1] if len(parts) > 1 else "",
                "checked_at": parts[2] if len(parts) > 2 else "",
            })
    # facts: "- text | attribution | url"
    for item in fields.get("facts", []):
        parts = _parse_list_item(item)
        if parts:
            payload["facts"].append({
                "text": parts[0],
                "attribution": parts[1] if len(parts) > 1 else "",
                "source_url": parts[2] if len(parts) > 2 else "",
            })

    # visual_plan: строки (в т.ч. нумерованные "1. ...")
    vp: list = []
    for block in fields.get("visual_plan", []):
        for ln in block.splitlines():
            ln = re.sub(r"^\s*\d+[.)]\s*", "", ln).strip()
            if ln:
                vp.append(ln)
    payload["visual_plan"] = vp

    # tags: инлайн через запятую и/или элементы списка
    tags: list = []
    for block in fields.get("tags", []):
        tags += [t.strip() for t in re.split(r"[,;]", block) if t.strip()]
    payload["tags"] = tags

    errors = validate_payload(payload)
    res.errors = errors
    if not errors:
        res.ok = True
        res.job = payload
        res.job_id = payload["job_id"]
        res.content_hash = content_hash(payload)
        res.dedupe_key = dedupe_key_for(payload)
        srcs = payload.get("sources") or []
        res.canonical_url = normalize_url(srcs[0]["url"]) if srcs else ""
    return res


def validate_payload(p: dict) -> list[str]:
    err: list[str] = []
    jid = p.get("job_id", "")
    if not jid:
        err.append("нет обязательного поля ID (job_id)")
    elif not ID_RE.match(jid):
        err.append(f"ID '{jid}' не подходит: строчные латиница/цифры/._-, длина 3-64")

    if not p.get("topic"):
        err.append("нет TOPIC (тема)")
    elif len(p["topic"]) > 160:
        err.append("TOPIC длиннее 160 символов")

    if not p.get("hook"):
        err.append("нет HOOK (хук)")
    elif len(p["hook"]) > 200:
        err.append("HOOK длиннее 200 символов")

    script = p.get("script", "")
    if not script:
        err.append("нет SCRIPT (сценарий)")
    elif len(script) < 120:
        err.append(f"SCRIPT слишком короткий ({len(script)} симв., минимум 120): не выйдет внятных 40-60 c")
    elif len(script) > 2600:
        err.append(f"SCRIPT слишком длинный ({len(script)} симв., максимум 2600): хронометраж уйдёт за ~90 c")

    if not p.get("sources"):
        err.append("нет SOURCES: нужен хотя бы один первоисточник с URL")
    else:
        for i, s in enumerate(p["sources"], 1):
            if not _URL_RE.match(s.get("url", "")):
                err.append(f"источник {i}: некорректный URL")
    checked = [s for s in p.get("sources", []) if s.get("checked_at")]
    if not checked:
        err.append("ни у одного источника нет checked_at (когда проверен первоисточник)")

    if not p.get("facts"):
        err.append("нет FACTS: нужен хотя бы один факт с атрибуцией")
    else:
        for i, f in enumerate(p["facts"], 1):
            if not f.get("text"):
                err.append(f"факт {i}: пустой текст")
            if not f.get("attribution"):
                err.append(f"факт {i}: нет атрибуции (кто/что подтверждает)")

    if p.get("language") not in ("ru", "uk", "en"):
        err.append(f"LANGUAGE '{p.get('language')}' не поддерживается (ru|uk|en)")

    if p.get("requested_mode") not in ("auto", "manual"):
        err.append("MODE должен быть auto | manual")
    return err


def extract_part_header(text: str) -> tuple[int, int, str] | None:
    """PART n/m в первых строках -> (n, m, текст без PART-строки)."""
    for i, line in enumerate(text.splitlines()[:3]):
        m = re.match(r"^PART\s*(\d+)\s*/\s*(\d+)\s*$", line.strip(), re.I)
        if m:
            rest = "\n".join(text.splitlines()[:i] + text.splitlines()[i + 1:])
            return int(m.group(1)), int(m.group(2)), rest
    return None
