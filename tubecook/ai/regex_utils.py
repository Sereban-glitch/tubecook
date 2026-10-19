"""Утилиты извлечения номеров судебных дел, картинок и контента из статей."""
from __future__ import annotations

import html
import re

CASE_NUMBER_PATTERNS = [
    r'(?:дело|справа|производство|постановление|рішення)\s*№?\s*(\d{3,4}/\d+/\d{2,4})',
    r'№\s*(\d{3,4}/\d+/\d{2,4})',
    r'\b(\d{3,4}/\d{3,6}/\d{2,4})\b',
]


def extract_case_numbers(text: str) -> list[str]:
    """Извлекает уникальные номера судебных дел из текста."""
    found = set()
    for pattern in CASE_NUMBER_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            num = match.group(1).strip()
            if num and len(num) >= 6:
                found.add(num)
    return sorted(found)


def strip_html(text: str) -> str:
    """Очищает HTML-теги и сущности."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def extract_article_body(html_content: str) -> str:
    """Извлекает основной содержательный текст статьи из HTML."""
    if not html_content:
        return ""

    # 1. Попытка через <article>
    m = re.search(r"<article[^>]*>(.*?)</article>", html_content, re.DOTALL | re.IGNORECASE)
    if m:
        body = strip_html(m.group(1))
        if len(body) > 300:
            return body

    # 2. Попытка через WordPress entry-content / content-inner
    m = re.search(r'class=["\'](?:entry-content|content-inner)[^"\']*["\'][^>]*>(.*?)</div>\s*(?:</div>|<footer)',
                  html_content, re.DOTALL | re.IGNORECASE)
    if m:
        body = strip_html(m.group(1))
        if len(body) > 300:
            return body

    # 3. Попытка через <main>
    m = re.search(r"<main[^>]*>(.*?)</main>", html_content, re.DOTALL | re.IGNORECASE)
    if m:
        body = strip_html(m.group(1))
        if len(body) > 300:
            return body

    # 4. Fallback: paragraphs
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html_content, re.DOTALL | re.IGNORECASE)
    chunks = [strip_html(p) for p in paras if len(strip_html(p)) > 40]
    if chunks:
        return "\n\n".join(chunks)

    return strip_html(html_content)


def extract_article_image(html_content: str) -> str | None:
    """Извлекает og:image или главное изображение статьи."""
    if not html_content:
        return None

    # og:image
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                  html_content, re.IGNORECASE)
    if m:
        url = m.group(1).strip()
        if url.startswith("http") and not url.endswith((".gif", "logo.png")):
            return url

    # twitter:image
    m = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                  html_content, re.IGNORECASE)
    if m:
        url = m.group(1).strip()
        if url.startswith("http"):
            return url

    # Первое изображение из wp-content/uploads/
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
    for img in imgs:
        if "wp-content/uploads" in img and not any(skip in img for skip in ("32x32", "150x150", "logo")):
            return img

    return None


def extract_youtube_link(html_content: str) -> str | None:
    """Извлекает ссылку на YouTube Shorts / видео из статьи."""
    if not html_content:
        return None
    m = re.search(r'(https?://(?:www\.)?youtube\.com/shorts/[a-zA-Z0-9_-]+)', html_content)
    if m:
        return m.group(1)
    m = re.search(r'(https?://youtu\.be/[a-zA-Z0-9_-]+)', html_content)
    if m:
        return m.group(1)
    return None
