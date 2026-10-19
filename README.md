# Tubecook v4.0 AI Edition

Автономный конвейер коротких вертикальных видео-новостей об ИИ:

**свежая проверенная новость → задание через Telegram → надёжная очередь (SQLite) →
выразительный ролик 1080x1920 с озвучкой и караоке-субтитрами →
предпросмотр/согласование → публикация в Telegram и YouTube Shorts.**

- Слоты публикаций: **00:00 / 06:00 / 12:00 / 18:00 Europe/Kyiv** (DST-корректно).
- Ручное согласование (HITL) — режим по умолчанию; автономный режим 4/день
  включается владельцем отдельно и только после первого показанного тестового выпуска.
- **Публикация по умолчанию выключена (dry-run)** — реальные API не вызываются,
  пока владелец явно не включит live.
- Целевое железо: HP ProBook 440 G3 (i5-6200U, HD Graphics 520, 12 ГБ, Linux Mint).
  VA-API используется автоматически при наличии `/dev/dri/renderD128`, иначе CPU.
  Проверка на вашей машине: `scripts/hp_bench.sh`.
- Бюджет: $0 на платные API. Edge-TTS (слова+тайминги), FFmpeg, Pillow,
  процедурная графика; стоковые медиа — через сменные адаптеры.

> Демо-ролики, отрендеренные этим кодом (песочница Z.ai, CPU), лежат рядом с архивом:
> `tubecook_v4_demo_base_1080x1920.mp4`, `tubecook_v4_demo_extended_1080x1920.mp4`
> и Telegram-версии 540x960. Сюжет помечен «ДЕМО • НЕ НОВОСТЬ».

## Состав пакета

```text
tubecook/            пакет (python >=3.10)
  config.py          конфигурация из .env (секреты только локально)
  db.py              SQLite WAL: jobs/publish_targets/assets/events/inbox
  protocol.py        протокол задания: разбор, валидация, дедуп-хеши, multipart
  queue.py           очередь: атомарный ACK, lease, retry/backoff, recovery, пауза
  scheduler.py       слоты Kyiv, DST, catch-up после сна, TTL свежести, пустая очередь
  security.py        роли (админ/отправитель), «данные ≠ команды»
  bot/core.py        транспорт-агностик бот-ядро (все команды, ACK, multipart)
  bot/console_adapter.py   тот же протокол через stdin (тесты/локальная работа)
  bot/telegram_adapter.py  aiogram 3.x (опция, ставится отдельно)
  media/tts.py       Edge-TTS + WordBoundary + детерминированный мок (оффлайн)
  media/ass.py       караоке-субтитры (пословная подсветка, mobile-safe)
  media/scenes.py    сценарий → сцены по смыслу фраз, тайминги по речи
  media/gfx.py       процедурная графика: фоны, карточки, параллакс-слой
  media/render.py    FFmpeg: сцены→xfade→субтитры→tpad-хвост; даккинг; R128
  media/deliver.py   Telegram-версия 540x960 ≤15 МБ (CRF-ladder), миниатюра
  publish/…          Telegram/YouTube: dry-run, uncertain, per-target статусы
  pipeline.py        claim → рендер (cancel-aware) → превью → публикация
  service.py         демон: транспорт + планировщик + воркер (потоки)
  cli.py             CLI: ingest/render/demo/status/approve/publish/bot/…
  import_v3.py       импорт заданий v3 (read-only)
tests/               81 тест (pytest) — вся логика без сети
examples/            demo_job.json + образец сообщения #TUBECOOK_JOB
deploy/              systemd-юниты + install.sh (установка рядом с v3)
scripts/             hp_bench.sh (VA-API/CPU замеры), run_tests.sh, make_demo.sh
docs/                протокол, облачное исследование, миграция, эксплуатация
assets/bgm/          royalty-free фоновая музыка (унаследована из v3)
```

## Быстрый старт (на ноутбуке)

```bash
# 0) системное (Linux Mint/Ubuntu)
sudo apt install -y ffmpeg vainfo intel-media-va-driver-non-free fonts-dejavu-core python3-venv

# 1) установка рядом с v3 (v3 не трогаем!)
cd ~/projects
tar xzf tubecook-v4.0.0-rc1.tar.gz && cd tubecook_v4
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2) конфиг
cp env.example .env
#   вписать ЛОКАЛЬНО: TUBECOOK_ADMINS=<ваш TG ID>, TUBECOOK_SENDERS=<ID Саши>
#   токены НЕ в чат, НЕ в репозиторий; всё остальное можно не менять

# 3) тесты (без сети, ~2 мин)
bash scripts/run_tests.sh

# 4) демо-ролик (та же озвучка, тот же сценарий, что в приложенных видео)
python -m tubecook.cli demo --profile base
python -m tubecook.cli demo --profile extended

# 5) сверка железа (VA-API vs CPU, время/RAM) — только на HP!
bash scripts/hp_bench.sh

# 6) живая работа
python -m tubecook.cli bot          # консольная сессия (протокол тот же, что в TG)
python -m tubecook.cli service      # демон: бот (если задан токен) + слоты + воркер
```

## Режимы и безопасность

| Параметр | По умолчанию | Смысл |
|---|---|---|
| `TUBECOOK_REQUIRE_APPROVAL` | true | HITL: превью Сергею, публикация после `/approve` |
| `TUBECOOK_AUTONOMOUS` | false | 4/день без подтверждений; включать после первого проверенного выпуска |
| `TUBECOOK_PUBLISH_LIVE` | false (dry-run) | реальные отправки; без токенов live-режим даёт явный сбой, а не тихий мок |

Правила доверия (проверяются тестами):
- отправители задаются Telegram ID (`TUBECOOK_ADMINS`, `TUBECOOK_SENDERS`) — это
  доступ, не секреты;
- `PRIORITY: high` и `AUTO_PUBLISH: true` из тела сообщения — **данные**,
  они не действуют без прав отправителя и включённых режимов;
- инструкции «поставь на паузу» внутри сценария остаются текстом, не командами;
- задания Сергея (админа) получают приоритет manual и уходят вне общей очереди.

## Протокол задания (кратко)

Сообщение боту начинается с `#TUBECOOK_JOB v4` (см. `SPEC_PROTOCOL.md` и
`examples/job_message.txt`): ID, TOPIC, HOOK, SCRIPT, SOURCES (с `checked_at`),
FACTS (с атрибуцией), VISUAL_PLAN, TAGS, LANGUAGE, MODE. Длинные задания —
частями `PART 1/2` / `PART 2/2`: ACK выдаётся только после приёма всей задачи.
Повтор того же ID/контента возвращает прежнюю квитанцию; конфликтующий payload
под тем же ID — ошибка без перезаписи; обновление новости — через `/allow-update`.

## Команды бота

`/status /job <id> /preview <id> /approve <id> /reject <id> /cancel <id>`
`/pause [причина] /resume /allow-update <id|url> /check <id> /test /mode /help`

## Проверенное и статус на целевом ноутбуке

- **Аппаратно проверено на ноутбуке HP ProBook 440 G3** (i5-6200U, Intel HD 520, Linux Mint 22.3):
  - **81 из 81 теста пройдены** (100% green).
  - Замер рендера VA-API (`/dev/dri/renderD128`): **204 сек (~3.4 мин)**, пиковое ОЗУ **926 МБ** (с запасом внутри лимита 3 ГБ).
  - Замер рендера CPU (`libx264`): 217 сек, пиковое ОЗУ 1.21 ГБ.
  - Длительности и синхронизация проверены: стоп-кадр `tpad` +0.9 сек защищает от обрыва звука, ASS караоке четкие.
  - Полный отчет замера: [`bench_report_20261019_0159.json`](bench_report_20261019_0159.json).
- **Следующий этап развития — модуль сбора новостей «Домдары» (`tubecook.ingest.domdara`):**
  - Полное ТЗ (Часть 1 — сбор, очередь, оффлайн): [`docs/SPEC_DOMDARA_INGEST.md`](docs/SPEC_DOMDARA_INGEST.md).
  - Уточнение ТЗ (Часть 2 — существующий ИИ-прокси и видеосценарий): [`docs/SPEC_DOMDARA_PART2_AI_SCRIPT.md`](docs/SPEC_DOMDARA_PART2_AI_SCRIPT.md).
  - Памятка текущего состояния и ограничений: [`docs/MEMO_STATUS.md`](docs/MEMO_STATUS.md).
  - Связанный репозиторий мониторинга и сбора: [bot_skaner_saitov](https://github.com/Sereban-glitch/bot_skaner_saitov) (коммит `84288b2`).
- **Безопасность и контроль:**
  - Автопубликация отключена (`require_approval = True`), реальные каналы не затронуты до личного просмотра владельцем первого ролика.
  - В репозитории нет токенов, .env с секретами, сессий и OAuth-файлов (проверено тестами `test_no_secrets.py`).

Подробнее: `docs/MEMO_STATUS.md` и `PROJECT_STATE.md`.

## Откат

v4 ставится в отдельный каталог и пишет в свою SQLite (`data/`). v3 и его
`build/`, `jobs/` не изменяются. Откат: `systemctl --user stop tubecook-v4`
(если ставили юниты) и вернуться к v3; данные v4 остаются в `data/` для разбора.

## Лицензия

MIT (унаследована от v3, автор Sereban-glitch). Медиа-ассеты: см. метаданные
лицензий в `docs/OPERATIONS.md` (BGM — royalty-free из состава v3; стоковые
клипы подключаются адаптерами с обязательным указанием URL/автора/лицензии).
