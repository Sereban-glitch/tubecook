"""Демон Tubecook v4: бот + планировщик + воркер в одном процессе.

Потоки (простые и надёжные на слабом CPU):
- transport: console (stdin) или aiogram-Telegram (если задан токен);
- scheduler: тик каждые 30 c (слоты Europe/Kyiv, catch-up, TTL, уведомления);
- worker: последовательный рендер (единственный исполнитель — lease в SQLite);
- recovery при старте: зависшие rendering/publishing возвращаются в очередь.
"""
from __future__ import annotations

import signal
import threading
import time

from tubecook import db as dbm
from tubecook.bot.console_adapter import run_console
from tubecook.bot.core import BotCore
from tubecook.config import Config
from tubecook.pipeline import Pipeline
from tubecook.publish.telegram_pub import TelegramPublisher
from tubecook.publish.youtube_pub import YouTubePublisher
from tubecook.queue import Queue
from tubecook.scheduler import Scheduler

STOP = threading.Event()


def main(cfg: Config, console: bool = False) -> None:
    conn = dbm.connect(cfg.db_path)
    dbm.migrate(conn)
    queue = Queue(conn, cfg)
    scheduler = Scheduler(conn, cfg, queue)
    publishers = {"telegram": TelegramPublisher(cfg),
                  "youtube": YouTubePublisher(cfg)}
    pipeline = Pipeline(cfg, queue, publishers=publishers)
    core = BotCore(cfg, queue, scheduler, pipeline, publishers)
    pipeline.bot = core

    requeued = queue.recovery(boot=True)
    if requeued:
        core.notify_admin(f"восстановление после перезапуска: в очередь "
                          f"возвращены {', '.join(requeued)} (счётчик попыток +1)")

    # --- транспорт
    if console or not cfg.telegram_bot_token:
        admin = next(iter(cfg.admin_ids), 0)
        threading.Thread(
            target=run_console, args=(core, admin), daemon=True,
            name="console").start()
    else:
        from tubecook.bot.telegram_adapter import TelegramTransport
        transport = TelegramTransport(core, cfg.telegram_bot_token)

        def _tg():
            import asyncio
            try:
                asyncio.run(transport.run())
            except Exception as e:   # падение транспорта не убивает сервис
                core.notify_admin(f"транспорт Telegram упал: {e}. Консоль: "
                                  "python -m tubecook.cli bot")
        threading.Thread(target=_tg, daemon=True, name="telegram").start()

    # --- планировщик
    def _scheduler_loop():
        while not STOP.is_set():
            try:
                tick = scheduler.tick()
                for jid, slot in tick.publish_now:
                    pipeline.publish_job(jid)
                for jid, new_slot in tick.shifted:
                    core.notify_admin(f"{jid}: слот сдвинут на {new_slot} "
                                      "(catch-up политика: не вываливаем "
                                      "ночную очередь залпом)")
                for text in tick.notify_admin:
                    core.notify_admin(text)
            except Exception as e:
                core.notify_admin(f"планировщик: сбой тика: {e}")
            STOP.wait(30)

    threading.Thread(target=_scheduler_loop, daemon=True,
                     name="scheduler").start()

    # --- воркер (рендер) — единственный исполнитель
    def _worker_loop():
        while not STOP.is_set():
            try:
                jid = pipeline.process_next()
                if jid is None:
                    STOP.wait(10)
            except Exception as e:
                core.notify_admin(f"воркер: сбой: {e}")
                STOP.wait(30)

    threading.Thread(target=_worker_loop, daemon=True, name="worker").start()

    def _stop(*_):
        STOP.set()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not STOP.is_set():
        time.sleep(1)
    conn.close()
