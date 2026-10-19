"""Консольный адаптер: тот же протокол, что в Telegram, но через stdin/stdout.

Назначение: локальная работа и тесты без токена; оператор = ID из TUBECOOK_ADMINS.
"""
from __future__ import annotations

import sys

from tubecook.bot.core import BotCore


def run_console(core: BotCore, admin_id: int, stdin=None, stdout=None) -> None:
    """Простой REPL: строка -> update -> ответы. stdin/stdout инъектируются в тестах."""
    inp = stdin or sys.stdin
    out = stdout or sys.stdout
    out.write("Tubecook v4 console. Введите задание (#TUBECOOK_JOB...) или /help.\n")
    out.flush()
    for line in inp:
        text = line.rstrip("\n")
        if not text:
            continue
        replies = core.handle_update({"sender_id": admin_id, "text": text})
        for r in replies:
            out.write(r["text"] + "\n")
            if r.get("file"):
                out.write(f"  [файл] {r['file']}\n")
        out.flush()
