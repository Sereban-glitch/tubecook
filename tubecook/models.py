"""Модели данных: состояния задания, цели публикации, задание и квитанция."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime


class JobState:
    """Состояния задания (ТЗ, раздел «Очередь»).

    accepted -> queued -> rendering -> rendered -> awaiting_approval
    -> publishing -> published;  из любого: failed / cancelled.
    """
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RENDERING = "rendering"
    RENDERED = "rendered"
    AWAITING_APPROVAL = "awaiting_approval"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = (ACCEPTED, QUEUED, RENDERING, RENDERED, AWAITING_APPROVAL,
           PUBLISHING, PUBLISHED, FAILED, CANCELLED)
    # активные = не завершённые (для дедупа)
    ACTIVE = (ACCEPTED, QUEUED, RENDERING, RENDERED, AWAITING_APPROVAL, PUBLISHING)


class TargetState:
    """Статус отдельной площадки (per-target, ТЗ)."""
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    UNCERTAIN = "uncertain"   # таймаут после отправки: возможно уже опубликовано
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"       # отправка не выполнялась (mock), НЕ считается публикацией

    ALL = (PENDING, SENDING, SENT, UNCERTAIN, FAILED, SKIPPED, DRY_RUN)


class Priority:
    MANUAL = "manual"   # тема/правка Сергея — выше автоматической очереди
    AUTO = "auto"


@dataclass
class Source:
    url: str
    published: str = ""      # ISO-дата публикации материала
    checked_at: str = ""     # когда Саша проверил первоисточник
    note: str = ""


@dataclass
class Fact:
    text: str
    attribution: str = ""    # кто/что подтверждает
    source_url: str = ""


@dataclass
class Job:
    job_id: str
    topic: str
    hook: str
    script: str
    sources: list = field(default_factory=list)    # list[dict] (Source)
    facts: list = field(default_factory=list)      # list[dict] (Fact)
    language: str = "ru"
    tags: list = field(default_factory=list)
    visual_plan: list = field(default_factory=list)
    requested_mode: str = "auto"     # запрошено отправителем (данные, не команда)
    requested_priority: str = ""     # PRIORITY из тела сообщения — только данные
    demo: bool = False               # демо/тестовый сюжет: НЕ публикуется как новость
    meta: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_payload(p: dict) -> "Job":
        known = {f for f in Job.__dataclass_fields__}
        return Job(**{k: v for k, v in p.items() if k in known})


@dataclass
class Receipt:
    """Квитанция ACK после атомарного сохранения."""
    job_id: str
    status: str                     # duplicate | conflict | accepted | error
    state: str = ""
    position: int = 0
    planned_slot: str = ""          # ISO с таймзоной
    content_hash: str = ""
    detail: str = ""
    created_at: str = ""

    def render_text(self) -> str:
        if self.status == "accepted":
            slot = f" | плановый слот: {self.planned_slot}" if self.planned_slot else ""
            return (f"OK принято: {self.job_id}\n"
                    f"статус: {self.state} (позиция {self.position}){slot}\n"
                    f"hash: {self.content_hash[:12]}")
        if self.status == "duplicate":
            return (f"DUPLICATE: задача уже принята как {self.job_id} "
                    f"(состояние {self.state}, hash {self.content_hash[:12]}).\n"
                    f"{self.detail}")
        if self.status == "conflict":
            return (f"CONFLICT: job_id {self.job_id} уже существует с ДРУГИМ содержимым.\n"
                    f"{self.detail}\nИспользуйте новый job_id.")
        return f"ERROR: {self.detail}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ts() -> float:
    return time.time()
