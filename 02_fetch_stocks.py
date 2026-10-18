#!/usr/bin/env python3
# ============================================================================
# 02_fetch_stocks.py v2.0 — сбор материалов для документального сериала.
# Четыре источника (все бесплатные, бюджет $0):
#   pexels          — видео по API-ключу (PEXELS_API_KEY), лицензия Pexels
#   wikimedia       — Архивные СТИЛЛЫ из Wikimedia Commons: фото/документы
#                     правительства США находятся в PUBLIC DOMAIN — идеально
#                     для сериала про рассекреченные операции. Ключ НЕ нужен.
#   openverse       — изображения CC0 без ключа
#   openverse-audio — эмбиент/шумы CC0 для саунд-дизайна (дрон, плёнка, дождь)
#
# Результат: <out>/*.mp4|jpg|ogg... + <out>/index.json — реестр лицензий
# (для сериала лицензия каждой секунды кадра должна быть доказуема).
#
# Использование:
#   python3 02_fetch_stocks.py --query "CIA building 1960" --source wikimedia
#   python3 02_fetch_stocks.py --query "dark drone ambient" --source openverse-audio
#   python3 02_fetch_stocks.py --query "vintage laboratory" --source pexels --count 4
# ============================================================================
import argparse
import json
import os
import sys
import time

import requests

PEXELS_API = "https://api.pexels.com/videos/search"
OPENVERSE_IMG = "https://api.openverse.org/v1/images/"
OPENVERSE_AUD = "https://api.openverse.org/v1/audio/"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
# Правило Wikimedia: ОБЯЗАТЕЛЬный описательный User-Agent, иначе 403
UA = "tubecook/2.0 (documentary shorts pipeline; educational; +github)"

# Лицензии Wikimedia, которые мы считаем безопасными для монетизации:
# public domain (снимки/документы Правительства США) и CC0.
PD_KEYS = ("public domain", "pd-usgov", "pd us", "cc0")


def log(msg: str) -> None:
    print(f"[stocks] {msg}", flush=True)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


# ------------------------------------------------------------------ pexels --
def fetch_pexels(query: str, count: int, api_key: str) -> list:
    """Видео с Pexels: портретные, высота >= 1080, НАИМЕНЬШИЙ достаточный файл."""
    items, page = [], 1
    s = _session()
    s.headers["Authorization"] = api_key
    while len(items) < count and page <= 3:
        r = s.get(PEXELS_API, params={
            "query": query, "per_page": min(80, count * 4), "page": page,
            "orientation": "portrait", "size": "medium"}, timeout=25)
        r.raise_for_status()
        for v in r.json().get("videos", []):
            best = None
            for f in v.get("video_files", []):
                if f.get("height", 0) >= 1080 and f.get("file_type") == "video/mp4":
                    if best is None or f["height"] < best["height"]:
                        best = f  # наименьший из >=1080 — экономия диска/RAM
            if best:
                items.append({
                    "url": best["link"],
                    "author": v.get("user", {}).get("name", "unknown"),
                    "pexels_id": v.get("id"),
                    "license": "Pexels License",
                    "source": "pexels", "kind": "video",
                })
            if len(items) >= count:
                break
        page += 1
        time.sleep(1.0)  # вежливый троттлинг 1 запрос/с
    return items


# --------------------------------------------------------------- wikimedia --
def fetch_wikimedia(query: str, count: int, min_width: int = 900) -> list:
    """Архивные стиллы из Commons. Фильтр: public domain / CC0, ширина >= 900px.

    Для сериала это главный источник: фотографии ЦРУ/Армии США рассекречены
    и находятся в PD-USGov — на них можно монетизироваться без рисков.
    """
    s = _session()
    r = s.get(WIKIMEDIA_API, params={
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6,            # 6 = File: (пространство файлов)
        "gsrlimit": min(count * 4, 40),
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": 1620,           # запрос thumbs 1620px под Ken-Burns 1080p
    }, timeout=25)
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}

    items, seen = [], set()
    # Сортировка: сперва Public Domain, затем CC0, затем всё остальное —
    # чтобы даже при слабом запросе наверху оказались юридически чистые файлы.
    def rank(it: dict) -> int:
        lic = it["license"].lower()
        if any(k in lic for k in PD_KEYS):
            return 0
        if "cc0" in lic:
            return 1
        return 2

    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii:
            continue
        w = ii.get("width", 0)
        if w < min_width:
            continue
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "unknown")
        # thumburl — уже пережатый сервером файл нужной ширины; если нет — оригинал
        url = ii.get("thumburl") or ii.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({
            "url": url,
            "author": (meta.get("Artist") or {}).get("value", "unknown"),
            "license": lic,
            "source": "wikimedia", "kind": "image",
            "title": p.get("title", ""),
            "width": w,
        })
    items.sort(key=rank)
    # Возврат: PD/CC0 первыми, лимит по количеству
    return items[:count]


# ---------------------------------------------------------------- openverse --
def fetch_openverse(query: str, count: int) -> list:
    """Изображения CC0 без ключа (анонимный лимит ~100 запр./день — берегите)."""
    r = requests.get(OPENVERSE_IMG, params={
        "q": query, "license": "cc0", "page_size": count,
        "aspect_ratio": "tall", "mature": "false"}, timeout=25,
        headers={"User-Agent": UA})
    r.raise_for_status()
    items = []
    for img in r.json().get("results", [])[:count]:
        items.append({
            "url": img["url"],
            "author": img.get("creator") or "unknown",
            "license": "CC0",
            "source": "openverse", "kind": "image",
            "title": img.get("title", ""),
        })
    return items


def fetch_openverse_audio(query: str, count: int = 3) -> list:
    """Эмбиент CC0 (дрон/хис/дождь) для атмосферного фона серий.

    Возвращаем прямые ссылки на аудио; ffmpeg понимает mp3/ogg/flac/wav,
    конвертация в 48k stereo выполняется стадией audio рендера.
    """
    r = requests.get(OPENVERSE_AUD, params={
        "q": query, "license": "cc0", "page_size": count * 2,
        "mature": "false"}, timeout=25, headers={"User-Agent": UA})
    r.raise_for_status()
    items = []
    for a in r.json().get("results", []):
        url = a.get("url") or ""
        if not url:
            continue
        ext = "." + url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in (".mp3", ".ogg", ".flac", ".wav"):
            continue  # пропускаем экзотику, которую не поднимет ffmpeg
        items.append({
            "url": url,
            "author": a.get("creator") or "unknown",
            "license": "CC0",
            "source": "openverse-audio", "kind": "audio",
            "title": a.get("title", ""),
            "ext": ext,
        })
        if len(items) >= count:
            break
    return items


# ---------------------------------------------------------------- download --
def _ext_of(item: dict) -> str:
    if item.get("ext"):
        return item["ext"]
    url = item["url"].split("?")[0]
    for e in (".mp4", ".jpg", ".jpeg", ".png", ".ogg", ".flac", ".wav", ".mp3"):
        if url.lower().endswith(e):
            return e
    return ".mp4" if item.get("kind") == "video" else ".jpg"


def download(items: list, out_dir: str, prefix: str = "stock") -> list:
    """Скачиваем и регистрируем каждый файл в index.json (перезапускаемо)."""
    index_path = os.path.join(out_dir, "index.json")
    index = []
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    known = {i["url"] for i in index}

    n = len(index)
    s = _session()
    for it in items:
        if it["url"] in known or len(index) >= 300:
            continue
        name = os.path.join(out_dir, f"{prefix}_{n:03d}{_ext_of(it)}")
        log(f"скачиваю {os.path.basename(name)} [{it['license']}] <- {it['url'][:70]}")
        try:
            with s.get(it["url"], stream=True, timeout=90) as r:
                r.raise_for_status()
                with open(name, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
        except requests.RequestException as e:
            log(f"  пропускаю ({e.__class__.__name__})")
            continue
        index.append({"file": name, **it})
        n += 1

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return index


# -------------------------------------------------------------------- main --
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Стоки: pexels / wikimedia (PD-архивы) / openverse / openverse-audio")
    ap.add_argument("--query", required=True, help="поисковая фраза (англ.)")
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument("--out", default="stocks")
    ap.add_argument("--prefix", default="stock", help="префикс имён файлов")
    ap.add_argument("--source", default="auto",
                    choices=["auto", "pexels", "openverse", "wikimedia",
                             "openverse-audio"])
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    key = os.environ.get("PEXELS_API_KEY", "")
    source = args.source
    if source == "auto":
        source = "pexels" if key else "wikimedia"

    if source == "pexels":
        if not key:
            log("PEXELS_API_KEY не задан (.env) — откатываюсь на wikimedia")
            source = "wikimedia"
        else:
            items = fetch_pexels(args.query, args.count, key)
            if len(items) < args.count:
                log(f"Pexels дал {len(items)} из {args.count} — добираем wikimedia")
                items += fetch_wikimedia(args.query, args.count - len(items))

    if source == "wikimedia":
        items = fetch_wikimedia(args.query, args.count)
        # Стиллов может не хватить на все сцены — добираем CC0-картинками
        if len(items) < args.count:
            items += fetch_openverse(args.query, args.count - len(items))
    elif source == "openverse":
        items = fetch_openverse(args.query, args.count)
    elif source == "openverse-audio":
        items = fetch_openverse_audio(args.query, args.count)

    index = download(items, args.out, args.prefix)
    fresh = index[-len(items):] if items else []
    pd_n = sum(1 for i in fresh if any(k in i.get("license", "").lower() for k in PD_KEYS))
    log(f"готово: {len(index)} файлов в {args.out}/, из них PD/CC0: {pd_n}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.HTTPError as e:
        print(f"[stocks] HTTP ошибка: {e}", file=sys.stderr)
        sys.exit(2)
