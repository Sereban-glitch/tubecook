"""Процедурная графика Tubecook v4 (Pillow): живые сцены вместо слайд-шоу.

Что рисуется:
- фон: тёмно-синий градиент + мягкие световые пятна + точечная сетка (seeded);
- карточки сцен: хук, факт с номером и атрибуцией, крупная цифра (stat),
  сравнение A/B, цитата, аутро с брендингом канала;
- слой акцентов: полупрозрачные фигуры по краям — для параллакс-дрейфа в ffmpeg;
- чип «ДЕМО • НЕ НОВОСТЬ» для тестовых сюжетов (обязателен по ТЗ).

Движение (зум фона, въезд карточки, дрейф акцентов, кроссфейды) накладывает
ffmpeg-граф (render.py). Красный «гриф рассекречено» из v3 удалён сознательно.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920

# палитра «AI-tech», без красного штампа
BG_TOP = (10, 16, 30)
BG_BOT = (22, 32, 56)
ACCENT = (34, 211, 238)      # циан
ACCENT2 = (167, 139, 250)    # фиолет
WHITE = (242, 246, 250)
GRAY = (148, 163, 184)
AMBER = (245, 158, 11)       # только для чипа ДЕМО
CARD_BG = (17, 27, 46)
CARD_BORDER = (56, 82, 122)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_fonts: dict = {}


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return _fonts[key]


def set_fonts(bold: str, regular: str) -> None:
    global FONT_BOLD, FONT_REG
    FONT_BOLD = bold or FONT_BOLD
    FONT_REG = regular or FONT_REG
    _fonts.clear()


# ------------------------------------------------------------------ текст

def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list:
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if draw.textlength(cand, font=font) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw: ImageDraw.ImageDraw, text: str, start_size: int, max_w: int,
             max_lines: int, min_size: int = 26, bold: bool = True):
    """Подбирает размер шрифта, чтобы текст влезал в max_lines строк."""
    size = start_size
    while size >= min_size:
        font = _font(size, bold)
        lines = wrap_text(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
        size -= 6
    font = _font(min_size, bold)
    return font, wrap_text(draw, text, font, max_w)


def _draw_center(draw, xy_center: tuple, text: str, font, fill, spacing: int = 14):
    x, y = xy_center
    lines = [text] if isinstance(text, str) else text
    total = sum(draw.textlength("Ag", font=font) and font.size + spacing
                for _ in lines) - spacing
    # высота строки ~ font.size; центрируем блок
    y0 = y - (len(lines) * (font.size + spacing) - spacing) / 2
    for i, ln in enumerate(lines):
        w = draw.textlength(ln, font=font)
        draw.text((x - w / 2, y0 + i * (font.size + spacing)), ln, font=font, fill=fill)


# ------------------------------------------------------------------ фон

def gradient_background(seed: int, w: int = W, h: int = H) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / h
        r = BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t
        g = BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t
        b = BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t
        for x in range(0, w, 2):
            px[x, y] = (int(r), int(g), int(b))
            if x + 1 < w:
                px[x + 1, y] = (int(r), int(g), int(b))

    # световые пятна
    blobs = Image.new("RGB", (w, h), (0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    for _ in range(3):
        cx, cy = rng.randint(0, w), rng.randint(int(h * 0.15), int(h * 0.85))
        rad = rng.randint(220, 420)
        col = rng.choice([(ACCENT[0] // 6, ACCENT[1] // 6, ACCENT[2] // 6),
                          (ACCENT2[0] // 7, ACCENT2[1] // 7, ACCENT2[2] // 7)])
        bd.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)
    blobs = blobs.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, Image.composite(blobs, img, Image.new("L", (w, h), 160)), 0.5)

    # точечная сетка
    d = ImageDraw.Draw(img, "RGBA")
    step = 84
    for gy in range(90, h, step):
        for gx in range(60, w, step):
            a = 26 + int(18 * math.sin(gx / 200 + gy / 300))
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(*ACCENT, max(18, a)))
    return img


# ------------------------------------------------------------------ карточки

def _card_base() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _rounded(d: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=2):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _chip(d: ImageDraw.ImageDraw, center_x: int, y: int, text: str,
          fill=(20, 40, 60, 235), fg=(*ACCENT, 255), pad=18, font_size=26):
    f = _font(font_size)
    w = d.textlength(text, font=f)
    box = [center_x - w / 2 - pad, y, center_x + w / 2 + pad, y + font_size + 2 * 12]
    _rounded(d, box, 14, fill)
    d.text((center_x - w / 2, y + 12), text, font=f, fill=fg)


def _demo_chip(canvas: Image.Image) -> None:
    d = ImageDraw.Draw(canvas)
    f = _font(30)
    text = "ДЕМО • НЕ НОВОСТЬ"
    w = d.textlength(text, font=f)
    box = [W - w - 76, 250, W - 40, 250 + 58]
    _rounded(d, box, 12, (*AMBER, 40), outline=(*AMBER, 220), width=2)
    d.text((box[0] + 18, 260), text, font=f, fill=(*AMBER, 255))


def hook_card(hook: str, source_note: str = "", demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    _chip(d, W // 2, 330, "AI • НОВОСТИ // РАЗБОР")
    font, lines = fit_text(d, hook, 92, 900, 4)
    _draw_center(d, (W // 2, 760), lines, font, (*WHITE, 255), spacing=18)
    # акцентная линия под хуком
    y = 760 + len(lines) * (font.size + 18) / 2 + 46
    d.rounded_rectangle([W // 2 - 160, y, W // 2 + 160, y + 12], radius=6,
                        fill=(*ACCENT, 255))
    if source_note:
        f = _font(30, bold=False)
        w = d.textlength(source_note, font=f)
        d.text((W // 2 - w / 2, y + 60), source_note, font=f, fill=(*GRAY, 230))
    if demo:
        _demo_chip(img)
    return img


# ------------------------------------------------------- фото и юршаблоны

def _cover_image(path: str, box_w: int, box_h: int, radius: int = 36) -> Image.Image:
    """Фото -> скруглённая обложка под бокс (cover-crop, без искажений)."""
    photo = Image.open(path).convert("RGB")
    src_w, src_h = photo.size
    scale = max(box_w / src_w, box_h / src_h)
    photo = photo.resize((max(box_w, int(src_w * scale + 0.5)),
                          max(box_h, int(src_h * scale + 0.5))),
                         Image.LANCZOS)
    pw, ph = photo.size
    left, top = (pw - box_w) // 2, (ph - box_h) // 2
    photo = photo.crop((left, top, left + box_w, top + box_h))
    mask = Image.new("L", (box_w, box_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, box_w, box_h], radius=radius,
                                            fill=255)
    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    out.paste(photo, (0, 0), mask)
    return out


def _photo_frame(img: Image.Image, path: str, box: list) -> bool:
    """Вставляет фото в скруглённую рамку с бордюром. False — файла нет."""
    try:
        x0, y0, x1, y1 = box
        cover = _cover_image(path, x1 - x0, y1 - y0)
    except Exception:
        return False
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0 - 6, y0 - 6, x1 + 6, y1 + 6], radius=42,
                        outline=(*CARD_BORDER, 255), width=6)
    img.alpha_composite(cover, (x0, y0))
    return True


def case_card(case_number: str, subtitle: str, text: str,
              points: list | None = None, demo: bool = False) -> Image.Image:
    """Юршаблон «Карточка дела»: номер крупно + суд + детали."""
    img = _card_base()
    d = ImageDraw.Draw(img)
    box = [90, 500, W - 90, 1350]
    _rounded(d, box, 44, (*CARD_BG, 248), outline=(*CARD_BORDER, 255), width=3)
    _chip(d, W // 2, box[1] + 70, "№ ДЕЛА", font_size=28)
    num = case_number or "—"
    font, _ = fit_text(d, num, 132, box[2] - box[0] - 160, 2)
    w = d.textlength(num, font=font)
    # свечение номера — как у stat-карточки
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((W / 2 - w / 2, box[1] + 150), num, font=font,
                              fill=(*ACCENT, 190))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    d.text((W / 2 - w / 2, box[1] + 150), num, font=font, fill=(*WHITE, 255))
    y = box[1] + 150 + font.size + 40
    d.rounded_rectangle([W // 2 - 130, y, W // 2 + 130, y + 10], radius=5,
                        fill=(*ACCENT, 255))
    y += 56
    if subtitle:
        sf, slines = fit_text(d, subtitle, 44, box[2] - box[0] - 140, 2)
        for ln in slines:
            lw = d.textlength(ln, font=sf)
            d.text((W / 2 - lw / 2, y), ln, font=sf, fill=(*ACCENT, 245))
            y += sf.size + 14
        y += 24
    body = points if points else ([text] if text else [])
    bf, blines = fit_text(d, " ".join(body), 40, box[2] - box[0] - 150, 5,
                          bold=False)
    for ln in blines:
        d.ellipse([box[0] + 64, y + 20, box[0] + 80, y + 36], fill=(*ACCENT2, 255))
        d.text((box[0] + 104, y), ln, font=bf, fill=(*WHITE, 250))
        y += bf.size + 16
    if demo:
        _demo_chip(img)
    return img


def verdict_card(points: list, text: str, demo: bool = False) -> Image.Image:
    """Юршаблон «Решение»: пункты-тезисы с акцентными маркерами."""
    img = _card_base()
    d = ImageDraw.Draw(img)
    box = [90, 520, W - 90, 1340]
    _rounded(d, box, 44, (*CARD_BG, 248), outline=(*ACCENT, 200), width=4)
    items = [p for p in (points or []) if p.strip()] or [text]
    y = box[1] + 90
    for i, point in enumerate(items[:5]):
        # маркер-галочка в акцентном круге
        cy = y + 26
        d.ellipse([box[0] + 52, cy - 30, box[0] + 112, cy + 30],
                  fill=(*ACCENT, 235))
        mf = _font(40)
        d.line([box[0] + 68, cy, box[0] + 80, cy + 12], fill=(10, 16, 30, 255), width=6)
        d.line([box[0] + 80, cy + 12, box[0] + 98, cy - 12], fill=(10, 16, 30, 255), width=6)
        pf, plines = fit_text(d, point, 46, box[2] - box[0] - 230, 3)
        for ln in plines:
            d.text((box[0] + 140, y), ln, font=pf, fill=(*WHITE, 255))
            y += pf.size + 12
        y += 34
        if y > box[3] - 120:
            break
    if demo:
        _demo_chip(img)
    return img


def problem_card(text: str, image: str = "", points: list | None = None,
                 demo: bool = False) -> Image.Image:
    """Юршаблон «Стороны спора»: фото в рамке + суть спора."""
    img = _card_base()
    d = ImageDraw.Draw(img)
    has_photo = bool(image) and _photo_frame(img, image, [120, 470, W - 120, 1240])
    if not has_photo:
        box = [90, 520, W - 90, 1300]
        _rounded(d, box, 44, (*CARD_BG, 248), outline=(*CARD_BORDER, 255), width=3)
        font, lines = fit_text(d, text, 54, box[2] - box[0] - 150, 6, bold=False)
        y = box[1] + 90
        for ln in lines:
            d.text((box[0] + 75, y), ln, font=font, fill=(*WHITE, 255))
            y += font.size + 16
    else:
        # плашка-подпись под фото: первые слова сути спора
        font, lines = fit_text(d, text, 44, W - 260, 3, bold=False)
        y = 1290
        for ln in lines:
            lw = d.textlength(ln, font=font)
            d.rounded_rectangle([W / 2 - lw / 2 - 26, y - 14, W / 2 + lw / 2 + 26,
                                 y + font.size + 12], radius=16,
                                fill=(*CARD_BG, 235))
            d.text((W / 2 - lw / 2, y), ln, font=font, fill=(*WHITE, 250))
            y += font.size + 26
    if demo:
        _demo_chip(img)
    return img


def steps_card(points: list, text: str, demo: bool = False) -> Image.Image:
    """Юршаблон «Практический вывод»: нумерованные шаги."""
    img = _card_base()
    d = ImageDraw.Draw(img)
    box = [90, 500, W - 90, 1360]
    _rounded(d, box, 44, (*CARD_BG, 248), outline=(*CARD_BORDER, 255), width=3)
    items = [p for p in (points or []) if p.strip()]
    if not items:
        items = [text]
    y = box[1] + 70
    for i, point in enumerate(items[:4], start=1):
        d.ellipse([box[0] + 50, y + 6, box[0] + 146, y + 102],
                  fill=(*ACCENT2, 235), outline=(*ACCENT2, 255), width=3)
        nf = _font(52)
        num = str(i)
        d.text((box[0] + 98 - d.textlength(num, font=nf) / 2, y + 22), num,
               font=nf, fill=(10, 16, 30, 255))
        pf, plines = fit_text(d, point, 44, box[2] - box[0] - 270, 3)
        for ln in plines:
            d.text((box[0] + 180, y + 10), ln, font=pf, fill=(*WHITE, 255))
            y += pf.size + 12
        y += 44
        if y > box[3] - 110:
            break
    if demo:
        _demo_chip(img)
    return img


def fact_card(index: int, text: str, attribution: str = "",
              demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    box = [90, 560, W - 90, 1330]
    _rounded(d, box, 44, (*CARD_BG, 232), outline=(*CARD_BORDER, 255), width=3)
    # номер
    nf = _font(58)
    d.ellipse([box[0] + 46, box[1] + 46, box[0] + 46 + 96, box[1] + 46 + 96],
              fill=(*ACCENT, 255))
    num = str(index)
    d.text((box[0] + 46 + 48 - d.textlength(num, font=nf) / 2, box[1] + 56),
           num, font=nf, fill=(10, 16, 30, 255))
    # текст факта
    font, lines = fit_text(d, text, 52, box[2] - box[0] - 170, 6, bold=False)
    y = box[1] + 170
    for ln in lines:
        d.text((box[0] + 60, y), ln, font=font, fill=(*WHITE, 255))
        y += font.size + 18
    # атрибуция
    if attribution:
        af = _font(30, bold=False)
        alines = wrap_text(d, "Источник: " + attribution, af, box[2] - box[0] - 120)
        ay = box[3] - 40 - len(alines) * (af.size + 10)
        for ln in alines:
            d.text((box[0] + 60, ay), ln, font=af, fill=(*GRAY, 235))
            ay += af.size + 10
    if demo:
        _demo_chip(img)
    return img


def stat_card(number: str, label: str, demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    # большая цифра с лёгким свечением
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    font, _ = fit_text(d, number, 210, 940, 2)
    w = d.textlength(number, font=font)
    gd.text((W / 2 - w / 2, 560), number, font=font, fill=(*ACCENT, 200))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.text((W / 2 - w / 2, 560), number, font=font, fill=(*WHITE, 255))
    # подпись
    font2, lines = fit_text(d, label, 46, 880, 4, bold=False)
    _draw_center(d, (W // 2, 1150), lines, font2, (*GRAY, 240), spacing=14)
    # мини-график роста
    base_x, base_y, bw, bh = 240, 1420, 600, 150
    d.rounded_rectangle([base_x - 30, base_y - 40, base_x + bw + 30, base_y + bh + 40],
                        radius=24, fill=(*CARD_BG, 200))
    n = 5
    for i in range(n):
        hgt = bh * (0.28 + 0.72 * i / (n - 1))
        x0 = base_x + i * (bw / n) + 12
        col = ACCENT if i < n - 1 else ACCENT2
        d.rounded_rectangle([x0, base_y + bh - hgt, x0 + bw / n - 24, base_y + bh],
                            radius=10, fill=(*col, 235))
    if demo:
        _demo_chip(img)
    return img


def compare_card(a_text: str, b_text: str, demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    panels = [(90, a_text, ACCENT), (W // 2 + 30, b_text, ACCENT2)]
    for px, text, col in panels:
        box = [px, 520, px + W // 2 - 130, 1290]
        _rounded(d, box, 36, (*CARD_BG, 232), outline=(*col, 210), width=3)
        font, lines = fit_text(d, text, 44, box[2] - box[0] - 70, 7, bold=False)
        y = box[1] + 120
        for ln in lines:
            d.text((box[0] + 40, y), ln, font=font, fill=(*WHITE, 255))
            y += font.size + 14
        d.rounded_rectangle([box[0] + 40, box[3] - 26, box[0] + 190, box[3] - 6],
                            radius=8, fill=(*col, 235))
    # бейдж VS
    vf = _font(64)
    d.ellipse([W // 2 - 74, 855, W // 2 + 74, 1005], fill=(10, 16, 30, 255),
              outline=(*ACCENT, 255), width=4)
    d.text((W // 2 - d.textlength("VS", font=vf) / 2, 878), "VS", font=vf,
           fill=(*WHITE, 255))
    if demo:
        _demo_chip(img)
    return img


def quote_card(text: str, demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    qf = _font(150)
    d.text((140, 430), "“", font=qf, fill=(*ACCENT, 180))
    font, lines = fit_text(d, text, 58, 820, 6, bold=False)
    _draw_center(d, (W // 2, 900), lines, font, (*WHITE, 255), spacing=20)
    d.rounded_rectangle([W // 2 - 110, 1330, W // 2 + 110, 1342], radius=6,
                        fill=(*ACCENT2, 255))
    if demo:
        _demo_chip(img)
    return img


def outro_card(channel: str, cta: str = "Подпишись", demo: bool = False) -> Image.Image:
    img = _card_base()
    d = ImageDraw.Draw(img)
    # лого-круг с инициалами
    initials = "".join(w[0] for w in channel.split()[:2]).upper() or "AI"
    lf = _font(96)
    d.ellipse([W // 2 - 110, 480, W // 2 + 110, 700], fill=(*CARD_BG, 255),
              outline=(*ACCENT, 255), width=5)
    d.text((W // 2 - d.textlength(initials, font=lf) / 2, 520), initials,
           font=lf, fill=(*ACCENT, 255))
    cf, clines = fit_text(d, channel, 56, 900, 2)
    _draw_center(d, (W // 2, 830), clines, cf, (*WHITE, 255), spacing=16)
    _chip(d, W // 2, 1010, cta + " • новые выпуски 4 раза в день")
    if demo:
        _demo_chip(img)
    return img


# ------------------------------------------------------------------ слой акцентов

def accent_layer(seed: int, w: int = W, h: int = H) -> Image.Image:
    """Полупрозрачные фигуры по краям кадра — для параллакс-дрейфа."""
    rng = random.Random(seed + 7)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(6, 9)):
        col = rng.choice([ACCENT, ACCENT2])
        alpha = rng.randint(26, 60)
        kind = rng.random()
        x, y = rng.randint(-60, w), rng.randint(int(h * 0.08), int(h * 0.92))
        if kind < 0.45:      # кольцо
            r = rng.randint(36, 110)
            d.ellipse([x - r, y - r, x + r, y + r], outline=(*col, alpha), width=3)
        elif kind < 0.75:    # плюс
            s = rng.randint(16, 34)
            lw = 4
            d.line([x - s, y, x + s, y], fill=(*col, alpha), width=lw)
            d.line([x, y - s, x, y + s], fill=(*col, alpha), width=lw)
        else:                # квадрат
            s = rng.randint(14, 30)
            d.rounded_rectangle([x - s, y - s, x + s, y + s], radius=6,
                                outline=(*col, alpha), width=3)
    return img.filter(ImageFilter.GaussianBlur(1))


# ------------------------------------------------------------------ сборка сцены

def render_scene_layers(scene: dict, cfg_font_bold=None, cfg_font_reg=None) -> dict:
    """Сцена (dict с kind и текстами) -> {bg: Path, card: Path, accent: Path}.

    Пишет PNG во временную папку scene['out_dir'].
    """
    if cfg_font_bold:
        set_fonts(cfg_font_bold, cfg_font_reg or cfg_font_bold)
    out = Path(scene["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    seed = scene.get("seed", 42)
    bg = gradient_background(seed)
    bg_path = out / f"bg_{scene['index']}.png"
    bg.save(bg_path)

    kind = scene["kind"]
    demo = scene.get("demo", False)
    if kind == "hook":
        card = hook_card(scene["text"], scene.get("note", ""), demo)
    elif kind == "fact":
        card = fact_card(scene.get("index", 1), scene["text"],
                         scene.get("attribution", ""), demo)
    elif kind == "stat":
        card = stat_card(scene.get("number", "…"), scene["text"], demo)
    elif kind == "compare":
        card = compare_card(scene.get("a", "A"), scene.get("b", "B"), demo)
    elif kind == "quote":
        card = quote_card(scene["text"], demo)
    elif kind == "case":
        card = case_card(scene.get("case_number", ""), scene.get("subtitle", ""),
                         scene["text"], scene.get("points") or [], demo)
    elif kind == "verdict":
        card = verdict_card(scene.get("points") or [], scene["text"], demo)
    elif kind == "problem":
        card = problem_card(scene["text"], scene.get("image", ""),
                            scene.get("points") or [], demo)
    elif kind == "practical_value":
        card = steps_card(scene.get("points") or [], scene["text"], demo)
    elif kind == "outro":
        card = outro_card(scene.get("channel", "Свободные люди Запорожья"),
                          demo=demo)
    else:
        card = fact_card(scene.get("index", 1), scene["text"], "", demo)
    card_path = out / f"card_{scene['index']}.png"
    card.save(card_path)

    accent_path = out / f"acc_{scene['index']}.png"
    accent_layer(seed).save(accent_path)
    return {"bg": bg_path, "card": card_path, "accent": accent_path}
