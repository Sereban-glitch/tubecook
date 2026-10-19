"""Transport-agnostic бот-ядро: команды, протокол заданий, ACK, multipart.

Адаптеры (console / aiogram-Telegram) приводят события к виду
{"sender_id": int, "text": str} и отправляют ответы ядра. Ядро не знает,
откуда пришло сообщение, — поэтому ВСЯ логика проверяется тестами без сети.

Мост «Саша -> конвейер» (ТЗ): обычное сообщение в Telegram-боте с видимым ACK.
Ни вебхуков, ни прямого API dots, ни доступа к ноутбуку у Саши нет и не нужно.
"""
from __future__ import annotations

import json
import sqlite3

from tubecook import db as dbm
from tubecook.models import JobState, now_iso
from tubecook.protocol import (ParseResult, extract_part_header, parse_message)
from tubecook.security import SenderRole, classify_sender

HELP = """Tubecook v4 — команды:
/status — состояние очереди
/job <id> — детали задания
/preview <id> — превью ролика (файлом)
/approve <id> — одобрить выпуск после рендера
/reject <id> [причина] — отклонить
/cancel <id> — снять из очереди (аудит сохраняется)
/pause [причина] — запретить публикации
/resume — снять паузу
/allow-update <id|url> — разрешить обновление новости (снимает дедуп)
/check <id> — сверить uncertain-публикации
/test — поставить в очередь демо-задание (помечено, не новость)
/mode — текущие режимы (dry-run/live, автономность, HITL)

Задание — сообщение с заголовком #TUBECOOK_JOB (формат в SPEC_PROTOCOL.md),
можно частями PART 1/2, PART 2/2. ACK выдаётся только после полного приёма."""

DEMO_JOB = {
    "job_id": "demo-tubecook-v4",
    "topic": "Демонстрация нового рендера Tubecook v4",
    "hook": "Тестовый сюжет: это демонстрация конвейера, а не новость",
    "script": (
        "Это демонстрационный сюжет Tubecook версии четыре. "
        "Он нужен, чтобы показать новый рендер без публикации в каналы. "
        "Субтитры подсвечиваются по словам на реальных таймингах озвучки. "
        "Видео собирается из осмысленных сцен с движением и параллаксом. "
        "Мастер рендерится в формате десять восемьдесят на тысяча девятьсот двадцать, тридцать кадров в секунду. "
        "Финальная фраза больше не обрывается: хвост добавляется стоп-кадром. "
        "Этот ролик помечен как демо и не является новостью. "
        "Подпишитесь на канал, чтобы увидеть настоящие выпуски."),
    "sources": [{"url": "https://github.com/Sereban-glitch/tubecook",
                 "published": "2026-10-18", "checked_at": "2026-10-18 12:00"}],
    "facts": [
        {"text": "Караоке-субтитры синхронизированы с границами слов озвучки",
         "attribution": "edge-tts WordBoundary", "source_url": ""},
        {"text": "Мастер 1080x1920 при 30 fps, Telegram-версия 540x960 до 15 МБ",
         "attribution": "спецификация Tubecook v4", "source_url": ""},
    ],
    "visual_plan": ["stat: 1080x1920"],
    "tags": ["tubecook", "демо"],
    "language": "ru",
    "requested_mode": "auto",
    "demo": True,
}


class BotCore:
    def __init__(self, cfg, queue, scheduler=None, pipeline=None, publishers=None):
        self.cfg = cfg
        self.queue = queue
        self.scheduler = scheduler
        self.pipeline = pipeline
        self.publishers = publishers or {}
        self.notifications: list[dict] = []   # для сервиса/адаптеров

    # ------------------------------------------------------------------ вход

    def handle_update(self, upd: dict) -> list[dict]:
        sender = int(upd.get("sender_id") or 0)
        text = (upd.get("text") or "").strip()
        role = classify_sender(sender, self.cfg)
        if not text:
            return []
        if text.startswith("/"):
            if role != SenderRole.ADMIN:
                self._event("unauthorized_command", None,
                            {"sender": sender, "cmd": text.split()[0]})
                return [{"text": "команды доступны только администратору"}]
            return self._command(sender, text)
        # не-команда: возможно, задание по протоколу
        return self._handle_job_text(sender, role, text)

    # ------------------------------------------------------------------ задания

    def _handle_job_text(self, sender: int, role: str, text: str) -> list[dict]:
        if role == SenderRole.UNKNOWN:
            self._event("unauthorized_job", None, {"sender": sender})
            return [{"text": "нет прав на отправку заданий. Обратитесь к владельцу "
                             "(ваш Telegram ID нужно добавить в TUBECOOK_SENDERS)."}]
        if "#TUBECOOK_JOB" not in text.upper():
            return [{"text": "не понял сообщение. Задание начинайте с #TUBECOOK_JOB; "
                             "команды — /help."}]

        part = extract_part_header(text)
        if part and part[1] > 1:
            return self._handle_multipart(sender, text, part)
        parsed = parse_message(text)
        return self._submit_parsed(sender, role, parsed, text)

    def _handle_multipart(self, sender: int, text: str, part: tuple) -> list[dict]:
        n, m, body = part
        parsed_probe = parse_message(body)
        jid = parsed_probe.job_id if parsed_probe.job_id else ""
        if not jid:
            for line in body.splitlines():
                if line.upper().startswith("ID:"):
                    jid = line.split(":", 1)[1].strip()
                    break
        if not jid:
            # часть без ID: если у отправителя ровно один незавершённый
            # multipart — относим часть к нему
            rows = self.queue.conn.execute(
                "SELECT DISTINCT job_id FROM inbox WHERE total > 1"
                " AND sender_id=?", (sender,)).fetchall()
            if len(rows) == 1:
                jid = rows[0]["job_id"]
        if not jid:
            return [{"text": "multipart: не найден ID задания — не могу связать части "
                             "(дублируйте строку ID: в каждой части)"}]
        with dbm.tx(self.queue.conn) as c:
            c.execute(
                "INSERT OR REPLACE INTO inbox(job_id, sender_id, part, total, text,"
                " received_at) VALUES (?,?,?,?,?,?)",
                (jid, sender, n, m, text, now_iso()))
        with dbm.tx(self.queue.conn) as c:
            rows = c.execute(
                "SELECT part, total, text FROM inbox WHERE job_id=? ORDER BY part",
                (jid,)).fetchall()
        total = rows[0]["total"] if rows else m
        got = {r["part"] for r in rows}
        if len(got) < total:
            missing = sorted(set(range(1, total + 1)) - got)
            return [{"text": f"часть {n}/{total} принята (job {jid}). "
                             f"Жду части: {', '.join(map(str, missing))}. "
                             "ACK будет выдан после получения всей задачи."}]
        assembled = "\n".join(r["text"] for r in rows)
        parsed = parse_message(assembled)
        replies = self._submit_parsed(sender, SenderRole.SENDER, parsed, assembled)
        # части отработаны — чистим (задание уже в БД целиком)
        with dbm.tx(self.queue.conn) as c:
            c.execute("DELETE FROM inbox WHERE job_id=?", (jid,))
        return replies

    def _submit_parsed(self, sender: int, role: str, parsed: ParseResult,
                       raw: str) -> list[dict]:
        if not parsed.ok:
            self._event("invalid_job", None, {"sender": sender,
                                              "errors": parsed.errors[:5]})
            return [{"text": "ОШИБКА ФОРМАТА: " + "; ".join(parsed.errors[:6])}]
        receipt = self.queue.submit(parsed.job, sender_id=sender, role=role)
        return [{"text": receipt.render_text()}]

    # ------------------------------------------------------------------ команды

    def _command(self, sender: int, text: str) -> list[dict]:
        parts = text.split()
        cmd = parts[0].lower().lstrip("/")
        arg = parts[1] if len(parts) > 1 else ""
        rest = " ".join(parts[2:])
        q = self.queue

        if cmd in ("start", "help"):
            return [{"text": HELP}]
        if cmd == "status":
            s = q.status_summary()
            paused = s.get("paused")
            lines = ["статус:", json.dumps(s["counts"], ensure_ascii=False),
                     f"в очереди: {s['queue_len']}"]
            if s.get("next"):
                lines.append(f"следующее: {s['next']['job_id']} "
                             f"({s['next']['priority']}, слот {s['next']['scheduled_slot']})")
            if paused:
                lines.append(f"ПАУЗА с {paused.get('at')}: {paused.get('reason')}")
            modes = []
            modes.append("LIVE" if not self.cfg.dry_run_publish else "DRY-RUN")
            modes.append("автономный" if self.cfg.autonomous_mode else "HITL (подтверждение)")
            lines.append("режим: " + ", ".join(modes))
            return [{"text": "\n".join(lines)}]
        if cmd == "job" and arg:
            row = q.get(arg)
            if not row:
                return [{"text": f"задание {arg} не найдено"}]
            targets = q.target_states(arg)
            return [{"text": json.dumps(
                {"job_id": row["job_id"], "state": row["state"],
                 "priority": row["priority"], "attempts": row["attempts"],
                 "slot": row["scheduled_slot"], "error": row["error"],
                 "targets": {k: v["state"] for k, v in targets.items()}},
                ensure_ascii=False, indent=1)}]
        if cmd == "pause":
            msg = q.pause(by=sender, reason=" ".join(parts[1:]))
            return [{"text": msg}]
        if cmd == "resume":
            return [{"text": q.resume(by=sender)}]
        if cmd == "cancel" and arg:
            r = q.cancel(arg, by=sender, reason=rest)
            return [{"text": r.render_text() if r.status != "error" else r.detail}]
        if cmd == "approve" and arg:
            r = q.approve(arg, admin_id=sender)
            return [{"text": r.detail or r.render_text()}]
        if cmd == "reject" and arg:
            r = q.cancel(arg, by=sender, reason="rejected: " + rest)
            return [{"text": "отклонено: " + arg + " (аудит сохранён)"}]
        if cmd == "allow-update" and arg:
            r = q.allow_update(sender, arg)
            return [{"text": r.detail or r.render_text()}]
        if cmd == "preview" and arg:
            return self._preview(arg)
        if cmd == "check" and arg:
            return self._check(arg)
        if cmd == "test":
            parsed = parse_message(_demo_message())
            return self._submit_parsed(sender, SenderRole.ADMIN, parsed, "")
        if cmd == "mode":
            return [{"text": json.dumps(
                {"dry_run_publish": self.cfg.dry_run_publish,
                 "autonomous_mode": self.cfg.autonomous_mode,
                 "require_approval": self.cfg.require_approval},
                ensure_ascii=False)}]
        return [{"text": "неизвестная команда. /help"}]

    def _preview(self, job_id: str) -> list[dict]:
        row = self.queue.get(job_id)
        if not row:
            return [{"text": f"задание {job_id} не найдено"}]
        if row["state"] not in (JobState.RENDERED, JobState.AWAITING_APPROVAL,
                                JobState.PUBLISHED, JobState.PUBLISHING):
            return [{"text": f"превью ещё не готово (состояние {row['state']})"}]
        tg = self.cfg.jobs_dir / job_id / "telegram.mp4"
        master = self.cfg.jobs_dir / job_id / "master.mp4"
        path = tg if tg.exists() else (master if master.exists() else None)
        if not path:
            return [{"text": "файлы превью не найдены (артефакты удалены?)"}]
        return [{"text": f"превью {job_id}:", "file": str(path)}]

    def _check(self, job_id: str) -> list[dict]:
        targets = self.queue.target_states(job_id)
        out = []
        for name, t in targets.items():
            if t["state"] == "uncertain":
                pub = self.publishers.get(name)
                res = pub.verify(job_id, t.get("result_ref") or "") if pub else None
                if res:
                    self.queue.set_target(job_id, name, res.state,
                                          result_ref=res.ref, error=res.error)
                    out.append(f"{name}: {res.state} "
                               f"({res.error or res.ref})")
                else:
                    out.append(f"{name}: verify недоступен, сверьте вручную")
            else:
                out.append(f"{name}: {t['state']}")
        return [{"text": "\n".join(out) or "целей нет"}]

    # ------------------------------------------------------------------ уведомления

    def notify_admin(self, text: str, file: str | None = None) -> None:
        """Уведомление админу через активный транспорт (кладём в очередь)."""
        self.notifications.append({"text": text, "file": file})

    def _event(self, kind: str, job_id, data: dict) -> None:
        try:
            dbm.event(self.queue.conn, kind, job_id, data)
        except sqlite3.Error:
            pass


def _demo_message() -> str:
    sources = "\n".join(f"- {s['url']} | {s['published']} | {s['checked_at']}"
                        for s in DEMO_JOB["sources"])
    facts = "\n".join(f"- {f['text']} | {f['attribution']} | "
                      f"{f.get('source_url', '')}" for f in DEMO_JOB["facts"])
    return f"""#TUBECOOK_JOB v4
ID: {DEMO_JOB['job_id']}
TOPIC: {DEMO_JOB['topic']}
HOOK: {DEMO_JOB['hook']}
SCRIPT:
{DEMO_JOB['script']}
SOURCES:
{sources}
FACTS:
{facts}
VISUAL_PLAN:
- stat: 1080x1920
TAGS: {", ".join(DEMO_JOB['tags'])}
LANGUAGE: ru
MODE: auto
DEMO: true"""
