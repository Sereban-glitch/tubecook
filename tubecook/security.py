"""Модель доверия: кто может что, и что НИКОГДА не берётся из тела сообщения.

Правила из ТЗ:
- авторизованные отправители и админ задаются стабильными Telegram ID (не токенами);
- Сергей (админ) имеет приоритет: его ручная тема/правка выше автоматической очереди;
- PRIORITY:high или AUTO_PUBLISH:true в теле сообщения — это ДАННЫЕ, не команды:
  они не действуют сами по себе, только в сочетании с правами отправителя
  и текущим глобальным режимом, который включается владельцем отдельно;
- рабочие инструкции внутри новости/URL/медиа — содержимое, а не управление.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SenderRole:
    UNKNOWN = "unknown"
    SENDER = "sender"      # авторизованный отправитель (например, Саша)
    ADMIN = "admin"        # владелец (Сергей)
    DOMDARA = "domdara"    # модуль сбора новостей Домдара
    SYSTEM = "system"      # внутренние системные задачи


def classify_sender(sender_id: int, cfg) -> str:
    if sender_id == -100:
        return SenderRole.DOMDARA
    if sender_id == 0:
        return SenderRole.SYSTEM
    if sender_id in cfg.admin_ids:
        return SenderRole.ADMIN
    if sender_id in cfg.allowed_sender_ids:
        return SenderRole.SENDER
    return SenderRole.UNKNOWN


def effective_priority(role: str, requested_priority: str) -> str:
    """manual дают только действия администратора (его сообщения и команды).

    PRIORITY: high из тела сообщения любого отправителя НИКОГДА не поднимает приоритет.
    """
    if role == SenderRole.ADMIN:
        # админ имеет право запросить manual; по умолчанию его задания тоже manual
        return "manual"
    if role == SenderRole.DOMDARA or requested_priority == "domdara":
        return "domdara"
    if requested_priority in ("ai_news", "auto"):
        return requested_priority
    return "auto"


def effective_mode(cfg, role: str, requested_mode: str, requested_auto_publish: bool) -> str:
    """Что реально произойдёт с публикацией.

    Возвращает 'approval' | 'auto' | 'reject':
    - reject: отправитель не авторизован;
    - approval: HITL — превью Сергею, публикация после /approve (режим по умолчанию);
    - auto: автономная публикация без подтверждения — только если владелец
      глобально включил autonomous_mode (отдельное осознанное действие).
    """
    if role == SenderRole.UNKNOWN:
        return "reject"
    if role == SenderRole.ADMIN and (requested_mode == "manual"):
        # ручная тема Сергея: всё равно требует одобрения, если HITL включён,
        # но публикуется вне общей очереди (priority=manual)
        return "auto" if (cfg.autonomous_mode and not cfg.require_approval) else "approval"
    if cfg.autonomous_mode and requested_auto_publish:
        return "auto"
    return "approval"


def command_from_text_allowed(role: str, text: str) -> bool:
    """Команды управления (/pause, /approve...) доступны админу.

    Инструкции вида «поставь на паузу», найденные ВНУТРИ новости/сценария,
    сюда не попадают: они не начинаются с '/' и остаются содержимым.
    """
    return role == SenderRole.ADMIN and text.startswith("/")
