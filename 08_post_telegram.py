#!/usr/bin/env python3
# ============================================================================
# 08_post_telegram.py — Дуал-формат кросс-постинга в Telegram канал.
# Отправляет:
#   1. Видеоролик (до 15 МБ) с потоковым faststart для мгновенного просмотра.
#   2. Подробное аналитическое досье (HTML-карточка расследования, архивные цитаты,
#      номера рассекреченных дел, факты и ссылки на документы).
#   3. Интерактивный Telegram-опрос (Poll) для взрывного вовлечения аудитории.
#
# Использование:
#   python3 08_post_telegram.py --manifest jobs/ep01_midnight_climax.json \
#                               --video build/ep01/out/preview_telegram.mp4
# ============================================================================
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse


def log(msg: str) -> None:
    print(f"[tg_post] {msg}", flush=True)


def tg_api_call(token: str, method: str, data: dict, files: dict = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    
    if files:
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = bytearray()
        for k, v in data.items():
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
        for field, (fname, fbytes, ftype) in files.items():
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\nContent-Type: {ftype}\r\n\r\n".encode("utf-8"))
            body.extend(fbytes)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        
        req = urllib.request.Request(url, data=bytes(body), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        })
    else:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json"
        })
        
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_dossier_text(m: dict) -> str:
    meta = m.get("historical_metadata", {})
    tp = m.get("telegram_post", {})
    
    title = tp.get("title") or m.get("title")
    lead = tp.get("lead") or m.get("hook")
    facts = tp.get("declassified_facts", [])
    facts_html = "\n".join(f"• {f}" for f in facts) if facts else "• Документы официально рассекречены правительством США."

    dossier = (
        f"<b>📁 ДЕЛО #{m.get('episode', 1):02d}: {title.upper()}</b>\n\n"
        f"<i>{lead}</i>\n\n"
        f"<b>🏛 Карточка рассекреченного дела:</b>\n"
        f"• <b>Ведомство:</b> {meta.get('agency', 'CIA / DoD')}\n"
        f"• <b>Период действия:</b> {meta.get('year_initiated', 'н/д')} гг.\n"
        f"• <b>Год снятия грифа:</b> {meta.get('year_declassified', '1977')} г.\n"
        f"• <b>Основание:</b> {meta.get('declassification_authority', 'Church Committee Hearings / FOIA')}\n"
        f"• <b>Ключевые фигуры:</b> {meta.get('key_figures', 'Секретный отдел')}\n"
        f"• <b>Архивный документ:</b> <code>{meta.get('primary_source_doc', 'DOD-FOIA-1997')}</code>\n\n"
        f"<b>⚡ Установленные факты:</b>\n{facts_html}\n\n"
        f"<b>💬 Обсуждение в комментариях:</b>\n"
        f"{tp.get('cta_question', 'Что из этого рассекреченного дела кажется вам наиболее невероятным?')}\n\n"
        f"#Рассекречено #История #Спецоперации #CIA #Документалистика"
    )
    return dossier


def main() -> int:
    ap = argparse.ArgumentParser(description="Дуал-постинг в Telegram-канал")
    ap.add_argument("--manifest", required=True, help="Путь к JSON-манифесту эпизода")
    ap.add_argument("--video", required=True, help="Путь к рендеру preview_telegram.mp4")
    ap.add_argument("--token", help="Telegram Bot Token (или переменная TELEGRAM_BOT_TOKEN)")
    ap.add_argument("--channel", help="ID/username канала (или TELEGRAM_CHANNEL_ID)")
    args = ap.parse_args()

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    channel = args.channel or os.environ.get("TELEGRAM_CHANNEL_ID")

    if not token or not channel:
        log("ОШИБКА: Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID в .env")
        return 1

    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)

    # 1. Отправка видеофайла
    log(f"Отправка видео {args.video} в канал {channel}...")
    with open(args.video, "rb") as vf:
        vbytes = vf.read()
    
    caption_short = f"🎬 <b>{m.get('title')}</b>\n\n<i>Смотрите полную версию в канале!</i>"
    v_res = tg_api_call(token, "sendVideo", {
        "chat_id": channel,
        "caption": caption_short,
        "parse_mode": "HTML",
        "supports_streaming": "true"
    }, files={"video": (os.path.basename(args.video), vbytes, "video/mp4")})
    log(f"Видео успешно опубликовано (msg_id: {v_res.get('result', {}).get('message_id')})")

    # 2. Публикация расширенного аналитического досье
    dossier_html = build_dossier_text(m)
    log("Публикация архивного досье...")
    d_res = tg_api_call(token, "sendMessage", {
        "chat_id": channel,
        "text": dossier_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    })
    log(f"Досье опубликовано (msg_id: {d_res.get('result', {}).get('message_id')})")

    # 3. Публикация интерактивного опроса
    poll_data = m.get("telegram_post", {}).get("poll")
    if poll_data and "question" in poll_data and "options" in poll_data:
        log("Публикация интерактивного опроса...")
        p_res = tg_api_call(token, "sendPoll", {
            "chat_id": channel,
            "question": poll_data["question"],
            "options": json.dumps(poll_data["options"]),
            "is_anonymous": "true"
        })
        log(f"Опрос создан (poll_id: {p_res.get('result', {}).get('poll', {}).get('id')})")

    log("Все публикации успешно размещены в Telegram!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
