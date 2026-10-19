"""Базовая семантика публикации (ТЗ «Публикация и подтверждения»).

Правила:
- dry_run по умолчанию: НИКАКОЙ отправки в сеть; результат пишется в outbox
  и помечается DRY_RUN — это НЕ публикация и никогда не называется ею;
- таймаут после отправки -> UNCERTAIN: материал МОЖЕТ быть уже опубликован.
  Никакого слепого повторного постинга; судьбу решает verify() или человек;
- частичный успех (Telegram прошёл, YouTube упал) -> повторяется ТОЛЬКО
  неуспешная площадка; видео/текст/опрос имеют отдельные статусы;
- exactly-once сторонние API не гарантируют — мы не обещаем.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TargetResult:
    target: str
    state: str            # TargetState.*
    ref: str = ""         # message_id / video id / путь к артефакту
    error: str = ""
    dry_run: bool = False


class Publisher:
    name = "base"

    def __init__(self, cfg):
        self.cfg = cfg

    def publish(self, job: dict, artifacts: dict) -> TargetResult:
        raise NotImplementedError

    def verify(self, job_id: str, ref: str) -> TargetResult:
        """Проверка uncertain-результата, если API это позволяет."""
        return TargetResult(self.name, "uncertain", ref=ref,
                            error="verify не реализован; нужен ручной /check")

    def _outbox(self) -> Path:
        p = Path(self.cfg.outbox_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def write_dry_run(self, job: dict, artifacts: dict, body: str) -> Path:
        """Пакет dry-run: что БЫЛО БЫ отправлено (файл + метка НЕ-публикации)."""
        jid = job["job_id"]
        path = self._outbox() / f"{jid}.{self.name}.dryrun.txt"
        path.write_text(
            "=== DRY-RUN: ЭТО НЕ ПУБЛИКАЦИЯ. Реальные API не вызывались. ===\n\n"
            + body, encoding="utf-8")
        return path
