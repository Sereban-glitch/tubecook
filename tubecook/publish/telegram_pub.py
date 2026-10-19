"""Публикация в Telegram: видео + пост с источниками + опрос.

Реальный режим требует TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID и включённый
live (TUBECOOK_PUBLISH_LIVE=true). По умолчанию — dry-run в outbox.

Uncertain: при таймауте sendVideo материал мог уйти; Telegram Bot API не даёт
надёжного способа проверить «наш» пост по message_id после разрыва — поэтому
статус uncertain и уведомление админу для ручной сверки (/check).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tubecook.models import TargetState
from tubecook.publish.base import Publisher, TargetResult

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_S = 60


def build_post_text(job: dict) -> tuple:
    """(html-пост с источниками, опрос или None)."""
    p = job
    lines = [f"<b>{p.get('topic', '')}</b>", ""]
    hook = p.get("hook", "")
    if hook:
        lines += [f"<i>{hook}</i>", ""]
    facts = p.get("facts", [])[:5]
    if facts:
        lines.append("<b>Факты:</b>")
        for f in facts:
            lines.append(f"• {f.get('text', '')}"
                         + (f" — {f.get('attribution', '')}"
                            if f.get("attribution") else ""))
        lines.append("")
    lines.append("<b>Источники:</b>")
    for s in p.get("sources", [])[:5]:
        url = s.get("url", "")
        lines.append(f"• {url}" + (f" (проверено {s.get('checked_at')})"
                                   if s.get("checked_at") else ""))
    tags = p.get("tags", [])
    if tags:
        lines += ["", " ".join(f"#{t.replace(' ', '_')}" for t in tags[:6])]
    poll = None
    q = p.get("meta", {}).get("poll")
    if isinstance(q, dict) and q.get("question") and q.get("options"):
        poll = q
    post = "\n".join(lines)
    if p.get("demo"):
        post = ("⚠️ ДЕМО-СЮЖЕТ (не новость)\n\n" + post)
    return post, poll


class TelegramPublisher(Publisher):
    name = "telegram"

    def publish(self, job: dict, artifacts: dict) -> TargetResult:
        post, poll = build_post_text(job)
        if self.cfg.dry_run_publish:
            video = artifacts.get("telegram_video")
            body = (f"канал: {self.cfg.tg_out.channel_id or '(не задан)'}\n"
                    f"видео: {video}\n\n"
                    f"--- текст поста ---\n{post}\n\n"
                    f"--- опрос ---\n{json.dumps(poll, ensure_ascii=False)}\n")
            path = self.write_dry_run(job, artifacts, body)
            return TargetResult(self.name, TargetState.DRY_RUN, ref=str(path),
                                dry_run=True)

        # live-режим: отсутствие токена/канала — явный сбой, не тихий dry-run
        if not self.cfg.telegram_bot_token or not self.cfg.tg_out.channel_id:
            return TargetResult(
                self.name, TargetState.FAILED,
                error="live-режим без TELEGRAM_BOT_TOKEN/TELEGRAM_CHANNEL_ID: "
                      "заполните .env (секреты только локально) и проверьте "
                      "права бота в канале")

        import requests
        token = self.cfg.telegram_bot_token
        chat = self.cfg.tg_out.channel_id
        video = artifacts.get("telegram_video")
        video_path = Path(video)
        if not video_path.exists():
            return TargetResult(self.name, TargetState.FAILED,
                                error=f"видео не найдено: {video}")
        if ff_size(video_path) > 50:
            return TargetResult(self.name, TargetState.FAILED,
                                error="видео больше 50 МБ (лимит sendVideo)")
        try:
            with open(video_path, "rb") as vf:
                r = requests.post(
                    API.format(token=token, method="sendVideo"),
                    data={"chat_id": chat,
                          "caption": (post[:1000] if post else "")[:1000],
                          "parse_mode": "HTML",
                          "supports_streaming": "true"},
                    files={"video": (video_path.name, vf, "video/mp4")},
                    timeout=TIMEOUT_S)
            r.raise_for_status()
            mid = r.json().get("result", {}).get("message_id")
            return self._send_rest(job, post, poll, chat, token, mid)
        except Exception as e:
            # таймаут после отправки: материал МОЖЕТ быть уже опубликован —
            # это uncertain, а не сбой (никакого слепого повторного постинга)
            if "timeout" in type(e).__name__.lower() or isinstance(e, TimeoutError):
                return TargetResult(self.name, TargetState.UNCERTAIN,
                                    error="таймаут sendVideo: возможно, видео "
                                          "опубликовано — сверьте канал вручную")
            return TargetResult(self.name, TargetState.FAILED, error=str(e)[:500])

    def _send_rest(self, job, post, poll, chat, token, mid) -> TargetResult:
        """Пост с источниками (reply на видео) и опрос — с отдельными статусами."""
        import requests
        try:
            r = requests.post(
                API.format(token=token, method="sendMessage"),
                json={"chat_id": chat, "text": post, "parse_mode": "HTML",
                      "reply_to_message_id": mid},
                timeout=TIMEOUT_S)
            r.raise_for_status()
        except Exception as e:
            # видео опубликовано, досье нет: частичный статус честно отражаем
            return TargetResult(self.name, TargetState.SENT, ref=str(mid),
                                error=f"видео OK (msg {mid}); пост не ушёл: "
                                      f"{str(e)[:200]}")
        if poll:
            try:
                rp = requests.post(
                    API.format(token=token, method="sendPoll"),
                    json={"chat_id": chat, "question": poll["question"],
                          "options": poll["options"], "is_anonymous": True},
                    timeout=TIMEOUT_S)
                rp.raise_for_status()
            except Exception as e:
                return TargetResult(self.name, TargetState.SENT, ref=str(mid),
                                    error=f"видео+пост OK; опрос не ушёл: "
                                          f"{str(e)[:200]}")
        return TargetResult(self.name, TargetState.SENT, ref=str(mid))


def ff_size(path) -> float:
    return Path(path).stat().st_size / (1024 * 1024)
