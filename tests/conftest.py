"""Общие фикстуры тестов Tubecook v4."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from tubecook import db as dbm
from tubecook.bot.core import BotCore
from tubecook.config import Config
from tubecook.queue import Queue

HAS_FFMPEG = shutil.which("ffmpeg") is not None

SAMPLE = """#TUBECOOK_JOB v4
ID: test-job-001
TOPIC: Тестовая тема конвейера
HOOK: Хук для теста протокола
SCRIPT:
Первое предложение достаточно длинное для теста. Второе предложение содержит цифру 42 для сцены со статистикой. Третье сравнивает локальные модели vs облачные сервисы. Четвёртое задаёт вопрос аудитории? Финальная фраза полностью завершает мысль.
SOURCES:
- https://example.com/post?utm_source=x | 2026-10-18 | 2026-10-18 10:00
FACTS:
- Факт один подтверждён | Источник: example.com | https://example.com/post
- Факт два тоже подтверждён | Источник: example.com
VISUAL_PLAN:
- stat: 42
TAGS: тест, протокол
LANGUAGE: ru
MODE: auto
AUTO_PUBLISH: true
"""

SAMPLE_PART1 = """#TUBECOOK_JOB v4
PART 1/2
ID: test-part-001
TOPIC: Многочастное задание для проверки протокола
HOOK: Хук многочастного задания
SOURCES:
- https://example.com/multi | 2026-10-18 | 2026-10-18 11:00
"""

SAMPLE_PART2 = """#TUBECOOK_JOB v4
PART 2/2
ID: test-part-001
SCRIPT:
Первое предложение многочастного задания достаточно длинное. Второе предложение несёт цифру 7 для теста сцены статистики. Третье предложение завершает сценарий с вопросом?
FACTS:
- Многочастный факт | Источник: example.com
LANGUAGE: ru
"""


@pytest.fixture
def cfg(tmp_path):
    c = Config(root=tmp_path)
    c.admin_ids = {111}
    c.allowed_sender_ids = {222}
    c.telegram_bot_token = ""
    c.dry_run_publish = True
    c.require_approval = True
    c.autonomous_mode = False
    c.voice = "ru-RU-DmitryNeural"
    return c.resolve()


@pytest.fixture
def q(cfg):
    conn = dbm.connect(cfg.db_path)
    dbm.migrate(conn)
    return Queue(conn, cfg)


@pytest.fixture
def core(cfg, q):
    return BotCore(cfg, q)


def words_of(text: str, step: float = 0.42) -> list:
    """Синтетические слова с равномерными таймингами (для тестов сцен/асс)."""
    out = []
    t = 0.05
    for w in text.split():
        out.append({"word": w, "start": round(t, 3),
                    "end": round(t + step * 0.8, 3)})
        t += step
    return out


def make_tiny_video(path, seconds: float = 2.0, w: int = 540, h: int = 960):
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440",
         "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True)
    return path
