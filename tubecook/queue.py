"""Транзакционная очередь заданий на SQLite: атомарный ACK, дедуп, lease, retry.

Гарантии (ТЗ «Очередь»):
- ACK выдаётся только после атомарного сохранения; повтор того же ID/hash
  возвращает ПРЕЖНЮЮ квитанцию; конфликтующий payload под тем же ID — ошибка
  без перезаписи;
- дедуп по нормализованному URL/содержанию; осознанное обновление новости —
  только через явный /allow-update от админа (новое задание вытесняет старое);
- единственный исполнитель = lease (owner + срок), восстановление после падения,
  ограниченный retry с backoff, аудит не стирается отменой.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime

from tubecook import db as dbm
from tubecook.config import Config
from tubecook.models import JobState, Priority, Receipt, now_iso
from tubecook.protocol import content_hash, dedupe_key_for


class _Signal(Exception):
    """Управляемый сигнал дедупа/конфликта (несёт готовую квитанцию)."""

    def __init__(self, receipt):
        super().__init__(receipt.status)
        self.receipt = receipt


class Queue:
    def __init__(self, conn: sqlite3.Connection, cfg: Config):
        self.conn = conn
        self.cfg = cfg

    # ------------------------------------------------------------------ submit

    def submit(self, payload: dict, sender_id: int, role: str,
               force_new: bool = False, supersedes: str | None = None) -> Receipt:
        """Атомарная постановка задания. Возвращает квитанцию (ACK).

        Рендер стартует сразу (буфер готовых выпусков — ТЗ), публикация
        ждёт плановый слот scheduled_slot.
        """
        jid = payload["job_id"]
        chash = content_hash(payload)
        dkey = payload.get("dedupe_key") or dedupe_key_for(payload)
        now = now_iso()
        planned_slot, _ = self._next_slot()
        due_at = time.time()          # рендер можно начинать немедленно

        from tubecook.security import effective_priority
        prio = effective_priority(role, payload.get("requested_priority", ""))

        def _insert(c: sqlite3.Connection) -> None:
            c.execute(
                "INSERT INTO jobs(job_id, dedupe_key, content_hash, state, priority,"
                " payload, created_at, updated_at, scheduled_slot, due_at, supersedes_job_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (jid, dkey, chash, JobState.QUEUED, prio,
                 json.dumps(payload, ensure_ascii=False), now, now, planned_slot,
                 due_at, supersedes))
            for tgt in ("telegram", "youtube"):
                c.execute(
                    "INSERT INTO publish_targets(job_id, target, state, updated_at)"
                    " VALUES (?,?,?,?)", (jid, tgt, "pending", now))
            dbm.event(c, "accepted", jid, {
                "sender": sender_id, "role": role, "priority": prio,
                "hash": chash[:12], "planned_slot": planned_slot,
                "demo": bool(payload.get("demo"))})

        try:
            with dbm.tx(self.conn) as c:
                self._dup_checks(c, jid, chash, dkey, force_new)
                _insert(c)
        except _Signal as sig:
            # события аудита — вне откаченной транзакции
            dbm.event(self.conn,
                      "conflict" if sig.receipt.status == "conflict"
                      else "duplicate_ignored",
                      jid, {"sender": sender_id,
                            "receipt_for": sig.receipt.job_id})
            return sig.receipt
        except sqlite3.IntegrityError:
            # dedupe_key занят ТЕРМИНАЛЬНЫМ заданием (cancelled/failed) —
            # новое вытесняет старое (осознанное обновление через allow-update
            # или повторная отправка после сбоя)
            old = self.conn.execute(
                "SELECT job_id, state FROM jobs WHERE dedupe_key=?", (dkey,)).fetchone()
            if old is None or old["state"] not in (JobState.CANCELLED, JobState.FAILED):
                raise
            with dbm.tx(self.conn) as c:
                c.execute("UPDATE jobs SET dedupe_key=? WHERE job_id=?",
                          (f"{dkey}|retired:{old['job_id']}", old["job_id"]))
                _insert(c)

        row = self.conn.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
        return self._receipt_from_row(row, "accepted")

    def _dup_checks(self, c, jid: str, chash: str, dkey: str,
                    force_new: bool) -> None:
        # 1) тот же job_id с другим содержимым -> конфликт, БЕЗ перезаписи
        row = c.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
        if row is not None:
            if row["content_hash"] == chash:
                # полный повтор: вернуть прежнюю квитанцию (идемпотентность)
                raise _Signal(self._receipt_from_row(row, "duplicate"))
            raise _Signal(Receipt(job_id=jid, status="conflict", detail=(
                f"job_id занят другим содержимым (hash {row['content_hash'][:12]} != {chash[:12]}); "
                "оригинал не изменён. Возьмите новый job_id.")))

        # 2) дедуп по каноническому URL / контенту среди АКТИВНЫХ заданий
        if not force_new:
            dup = c.execute(
                "SELECT * FROM jobs WHERE dedupe_key=? AND state IN "
                "(?,?,?,?,?,?) ORDER BY created_at DESC LIMIT 1",
                (dkey, *JobState.ACTIVE)).fetchone()
            if dup is not None:
                raise _Signal(Receipt(
                    job_id=dup["job_id"], status="duplicate",
                    state=dup["state"], content_hash=dup["content_hash"],
                    created_at=dup["created_at"],
                    detail=(f"новый job_id {jid} отклонён как дубль; "
                            "для осознанного обновления новости: /allow-update "
                            f"{dup['job_id']} (админ).")))

    def allow_update(self, admin_id: int, ref: str) -> Receipt:
        """/allow-update <job_id|url>: снять дедуп-блок (осознанное обновление новости).

        Помечает существующее задание cancelled (аудит остаётся) и разрешает
        следующую отправку с тем же URL/контентом создать НОВОЕ задание.
        """
        ref = ref.strip()
        with dbm.tx(self.conn) as c:
            row = None
            if ref:
                row = c.execute("SELECT * FROM jobs WHERE job_id=?", (ref,)).fetchone()
            if row is None and ref.startswith("http"):
                from tubecook.protocol import normalize_url
                dkey = "url:" + hashlib.sha256(
                    normalize_url(ref).encode()).hexdigest()[:24]
                row = c.execute(
                    "SELECT * FROM jobs WHERE dedupe_key=? ORDER BY created_at DESC LIMIT 1",
                    (dkey,)).fetchone()
            if row is None:
                return Receipt(job_id=ref, status="error",
                               detail="не найдено задание/URL для allow-update")
            dbm.event(c, "allow_update", row["job_id"], {"admin": admin_id})
            c.execute("UPDATE jobs SET state=?, updated_at=? WHERE job_id=?",
                      (JobState.CANCELLED, now_iso(), row["job_id"]))
            dbm.event(c, "cancelled", row["job_id"],
                      {"reason": "allow_update: разрешено обновление новости",
                       "admin": admin_id})
        return Receipt(job_id=row["job_id"], status="accepted", state="cancelled",
                       detail=f"дедуп-блок снят для {row['job_id']}; "
                              "можно присылать обновлённое задание (новый job_id)")

    # ------------------------------------------------------------------ claim/lease

    def claim(self, owner: str | None = None, now: float | None = None) -> sqlite3.Row | None:
        """Забрать следующее задание в rendering с lease (единственный исполнитель).

        Порядок: manual выше auto; внутри — по времени готовности (due_at), затем FIFO.
        Задания на retry с будущим due_at не забираются. Зависший rendering
        разбирается recovery() — lease takeover не молчит в аудите.
        """
        owner = owner or f"worker-{uuid.uuid4().hex[:8]}"
        now = now if now is not None else time.time()
        lease_until = now + self.cfg.lease_s
        with dbm.tx(self.conn) as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE state=?"
                " AND (due_at IS NULL OR due_at <= ?)"
                " ORDER BY CASE priority WHEN 'manual' THEN 0 WHEN 'ai_news' THEN 1 WHEN 'auto' THEN 2 WHEN 'domdara' THEN 3 ELSE 4 END,"
                " due_at ASC, created_at ASC LIMIT 1",
                (JobState.QUEUED, now)).fetchone()
            if row is None:
                return None
            attempts = row["attempts"]
            c.execute(
                "UPDATE jobs SET state=?, lease_owner=?, lease_until=?,"
                " updated_at=? WHERE job_id=?",
                (JobState.RENDERING, owner, lease_until, now_iso(), row["job_id"]))
            dbm.event(c, "claimed", row["job_id"], {"owner": owner})
        return self.conn.execute("SELECT * FROM jobs WHERE job_id=?",
                                 (row["job_id"],)).fetchone()

    def heartbeat(self, job_id: str, owner: str) -> None:
        with dbm.tx(self.conn) as c:
            c.execute("UPDATE jobs SET lease_until=? WHERE job_id=? AND lease_owner=?",
                      (time.time() + self.cfg.lease_s, job_id, owner))

    def complete_stage(self, job_id: str, state: str, owner: str) -> None:
        """Перевод в стабильное состояние (rendered / awaiting_approval / ...) со снятием lease."""
        with dbm.tx(self.conn) as c:
            c.execute("UPDATE jobs SET state=?, lease_until=NULL, lease_owner=NULL,"
                      " updated_at=? WHERE job_id=?", (state, now_iso(), job_id))
            dbm.event(c, f"state:{state}", job_id, {"owner": owner})

    def fail(self, job_id: str, error: str, owner: str) -> Receipt:
        """Сбой: retry с backoff или failed после max_attempts. Аудит сохраняется."""
        with dbm.tx(self.conn) as c:
            row = c.execute("SELECT attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            attempts = row["attempts"] + 1 if row else 1
            if attempts >= self.cfg.max_attempts:
                c.execute("UPDATE jobs SET state=?, attempts=?, error=?,"
                          " lease_until=NULL, lease_owner=NULL, updated_at=? WHERE job_id=?",
                          (JobState.FAILED, attempts, error[:2000], now_iso(), job_id))
                dbm.event(c, "failed_final", job_id, {"error": error[:500],
                                                      "attempts": attempts})
                return Receipt(job_id=job_id, status="error", state=JobState.FAILED,
                               detail=f"попытки исчерпаны ({attempts}): {error[:200]}")
            backoff = self.cfg.backoff_s[min(attempts - 1, len(self.cfg.backoff_s) - 1)]
            next_try = datetime.fromtimestamp(time.time() + backoff,
                                              tz=self.cfg.tz).isoformat(timespec="seconds")
            c.execute("UPDATE jobs SET state=?, attempts=?, error=?, lease_until=NULL,"
                      " lease_owner=NULL, scheduled_slot=?, due_at=?, updated_at=? WHERE job_id=?",
                      (JobState.QUEUED, attempts, error[:2000], next_try,
                       time.time() + backoff, now_iso(), job_id))
            dbm.event(c, "failed_retry", job_id, {"error": error[:500],
                                                   "attempts": attempts, "retry_at": next_try})
            return Receipt(job_id=job_id, status="error", state=JobState.QUEUED,
                           detail=f"попытка {attempts}/{self.cfg.max_attempts}, повтор {next_try}")

    def cancel(self, job_id: str, by: str, reason: str = "") -> Receipt:
        """Отмена: задание -> cancelled; аудит НЕ стирается."""
        with dbm.tx(self.conn) as c:
            row = c.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return Receipt(job_id=job_id, status="error", detail="задание не найдено")
            if row["state"] in (JobState.PUBLISHED,):
                return Receipt(job_id=job_id, status="error", state=JobState.PUBLISHED,
                               detail="уже опубликовано — отмена невозможна")
            c.execute("UPDATE jobs SET state=?, lease_until=NULL, lease_owner=NULL,"
                      " updated_at=? WHERE job_id=?",
                      (JobState.CANCELLED, now_iso(), job_id))
            dbm.event(c, "cancelled", job_id, {"by": by, "reason": reason})
        return Receipt(job_id=job_id, status="accepted", state=JobState.CANCELLED,
                       detail="отменено (аудит сохранён)")

    # ------------------------------------------------------------------ пауза

    def pause(self, by: str, reason: str = "") -> str:
        """Пауза: немедленно запретить НОВЫЕ публикации.

        Судьба начатого: рендер доезжает до rendered и ждёт; шаг публикации
        не стартует, пока пауза стоит.
        """
        with dbm.tx(self.conn) as c:
            dbm.set_meta(c, "paused", json.dumps({"by": by, "reason": reason,
                                                  "at": now_iso()}))
            dbm.event(c, "paused", None, {"by": by, "reason": reason})
        return ("пауза включена: новые публикации запрещены. Начатый рендер "
                "будет доведён до состояния rendered и остановится перед "
                "публикацией; возобновление — /resume.")

    def resume(self, by: str) -> str:
        with dbm.tx(self.conn) as c:
            dbm.set_meta(c, "paused", "")
            dbm.event(c, "resumed", None, {"by": by})
        return "пауза снята: планировщик продолжит работу."

    def is_paused(self) -> dict | None:
        raw = dbm.get_meta(self.conn, "paused", "") or ""
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"by": "?", "reason": "", "at": ""}

    # ------------------------------------------------------------------ публикация

    def approve(self, job_id: str, admin_id: int) -> Receipt:
        """/approve: рендер уже готов; разрешение на публикацию в свой слот."""
        with dbm.tx(self.conn) as c:
            row = c.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return Receipt(job_id=job_id, status="error", detail="задание не найдено")
            if row["state"] != JobState.RENDERED:
                return Receipt(job_id=job_id, status="error", state=row["state"],
                               detail=(f"одобрение возможно только после рендера "
                                       f"(текущее состояние: {row['state']})"))
            dbm.event(c, "approved", job_id, {"admin": admin_id})
        return Receipt(job_id=job_id, status="accepted", state=JobState.RENDERED,
                       detail="одобрено: выйдет в ближайший слот (manual — сразу)")

    def _shift_slot(self, job_id: str, new_slot_dt) -> None:
        with dbm.tx(self.conn) as c:
            c.execute("UPDATE jobs SET scheduled_slot=?, due_at=?, updated_at=? WHERE job_id=?",
                      (new_slot_dt.isoformat(timespec="seconds"), new_slot_dt.timestamp(),
                       now_iso(), job_id))

    def set_target(self, job_id: str, target: str, state: str,
                   result_ref: str = "", error: str = "", attempts: int | None = None) -> None:
        with dbm.tx(self.conn) as c:
            c.execute(
                "UPDATE publish_targets SET state=?, result_ref=?, last_error=?,"
                " updated_at=?, attempts=COALESCE(?, attempts) WHERE job_id=? AND target=?",
                (state, result_ref, error[:1000] if error else None, now_iso(),
                 attempts, job_id, target))
            dbm.event(c, f"target:{target}:{state}", job_id,
                      {"ref": result_ref, "error": error[:300]})

    def target_states(self, job_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT target, state, result_ref, last_error FROM publish_targets"
            " WHERE job_id=?", (job_id,)).fetchall()
        return {r["target"]: dict(r) for r in rows}

    def mark_publishing(self, job_id: str, owner: str) -> None:
        with dbm.tx(self.conn) as c:
            c.execute("UPDATE jobs SET state=?, lease_owner=?, lease_until=?,"
                      " updated_at=? WHERE job_id=?",
                      (JobState.PUBLISHING, owner,
                       time.time() + self.cfg.lease_s, now_iso(), job_id))

    def mark_published(self, job_id: str) -> None:
        with dbm.tx(self.conn) as c:
            c.execute("UPDATE jobs SET state=?, updated_at=? WHERE job_id=?",
                      (JobState.PUBLISHED, now_iso(), job_id))
            dbm.event(c, "published", job_id, {})

    def set_awaiting_approval(self, job_id: str) -> None:
        self.complete_stage(job_id, JobState.AWAITING_APPROVAL, "pipeline")

    # ------------------------------------------------------------------ recovery

    def recovery(self, boot: bool = False) -> list[str]:
        """Восстановление после падения/перезапуска (sleep/restart).

        - rendering/publishing с истёкшим lease -> обратно в queued (попытка+1,
          backoff), рендер возобновится по артефактам;
        - цели в состоянии uncertain НЕ перевыставляются автоматически:
          их судьбу решает verify (см. publish/base.py) или человек.
        """
        touched: list[str] = []
        now = time.time()
        rows = self.conn.execute(
            "SELECT job_id, state, lease_until FROM jobs WHERE state IN (?,?)",
            (JobState.RENDERING, JobState.PUBLISHING)).fetchall()
        for row in rows:
            lease = row["lease_until"]
            stale = (lease is None) or (lease < now)
            if stale:
                touched.append(row["job_id"])
                # fail() открывает собственную транзакцию — не вкладываем
                self.fail(row["job_id"], "восстановление: lease истёк/процесс умер",
                          "recovery")
        if boot:
            dbm.event(self.conn, "recovery_boot", None, {"requeued": touched})
        return touched

    # ------------------------------------------------------------------ статус

    def status_summary(self) -> dict:
        counts: dict = {}
        for row in self.conn.execute(
                "SELECT state, COUNT(*) AS n FROM jobs GROUP BY state"):
            counts[row["state"]] = row["n"]
        queue_len = self.conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state IN (?,?)",
            (JobState.QUEUED, JobState.ACCEPTED)).fetchone()["n"]
        next_job = self.conn.execute(
            "SELECT job_id, priority, scheduled_slot FROM jobs WHERE state IN (?,?)"
            " ORDER BY CASE priority WHEN 'manual' THEN 0 ELSE 1 END,"
            " scheduled_slot ASC, created_at ASC LIMIT 1",
            (JobState.QUEUED, JobState.ACCEPTED)).fetchone()
        return {
            "counts": counts,
            "queue_len": queue_len,
            "next": dict(next_job) if next_job else None,
            "paused": self.is_paused(),
        }

    def get(self, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()

    def position_of(self, job_id: str) -> int:
        """Позиция среди готовых к работе заданий (для квитанции)."""
        rows = self.conn.execute(
            "SELECT job_id, priority, due_at, created_at FROM jobs WHERE state IN (?,?)"
            " ORDER BY CASE priority WHEN 'manual' THEN 0 ELSE 1 END,"
            " due_at ASC, created_at ASC",
            (JobState.QUEUED, JobState.ACCEPTED)).fetchall()
        for i, r in enumerate(rows, 1):
            if r["job_id"] == job_id:
                return i
        return len(rows) + 1

    # ------------------------------------------------------------------ внутреннее

    def _next_slot(self) -> tuple[str, float]:
        from tubecook.scheduler import next_slot
        dt = next_slot(self.cfg)
        return dt.isoformat(timespec="seconds"), dt.timestamp()

    def _receipt_from_row(self, row: sqlite3.Row, status: str) -> Receipt:
        return Receipt(
            job_id=row["job_id"], status=status, state=row["state"],
            position=self.position_of(row["job_id"]) if status == "accepted" else 0,
            planned_slot=row["scheduled_slot"] or "",
            content_hash=row["content_hash"], created_at=row["created_at"])
