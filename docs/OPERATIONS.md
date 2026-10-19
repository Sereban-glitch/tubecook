# Эксплуатация Tubecook v4

## Служба (systemd user)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/tubecook-v4.service deploy/tubecook-v4.timer ~/.config/systemd/user/
systemctl --user daemon-reload
# основной режим — постоянный демон (бот-поллинг + планировщик + воркер):
systemctl --user enable --now tubecook-v4.service
# альтернатива (минимальная) — пробуждения таймером:
# systemctl --user enable --now tubecook-v4.timer
journalctl --user -u tubecook-v4.service -f
```

`install.sh` делает то же самое автоматически (установка venv + юниты).

## Питание и сон ноутбука (рекомендации, сами настройки не меняем)

- Сон = демона нет = слоты пропускаются. После пробуждения `tubecook-v4.service`
  стартует автоматически (Restart=always), очередь восстанавливается (recovery),
  пропущенные слоты обрабатываются политикой catch-up: максимум 1 выпуск,
  остальные сдвигаются; протухшие по TTL новости не публикуются (уведомление).
- Рекомендации (вручную, по желанию): `sudo systemctl mask sleep.target` —
  только если ноутбук должен работать ночью; либо смириться с пропуском
  ночных слотов (политика уже корректна). Настройки питания — решение владельца.
- Охлаждение: рендер грузит 2 ядра; сервис ставит `-filter_complex_threads 1`
  и кодирует veryfast — пик RAM <1 ГБ.

## Ротация и бэкап

- Всё состояние — `data/tubecook.db` (SQLite WAL) + артефакты `data/jobs/`.
- Бэкап: `sqlite3 data/tubecook.db ".backup data/backup.db"` или просто копия
  каталога `data/` при остановленной службе.
- Артефакты рендера каждого выпуска (`master.mp4`, `telegram.mp4`, `thumb.jpg`,
  `render_report.json`, сцены) лежат в `data/jobs/<job_id>/`; удалять можно
  вручную после публикации, отчёты копируйте в архив отдельно.

## Лицензии медиа (обязательная таблица для каждого выпуска)

Формат хранения метаданных — таблица `assets` (SQLite): для каждого актива
URL, автор, лицензия и её версия, требуемая атрибуция, дата, преобразования.

- BGM v4.1: `news_loop.mp3`, `legal_loop.mp3`, `tech_loop.mp3` — сгенерированы
  процедурно `scripts/make_bgm.py` (numpy, без внешних сервисов и сэмплов) —
  права чистые, воспроизводимы детерминированно; выбор через `TUBECOOK_BGM`
  (news|legal|tech|legacy|none|путь), громкость `TUBECOOK_BGM_VOLUME`.
  `assets/bgm/soft_loop.mp3` (legacy) — «royalty-free» из состава v3; владелец
  должен подтвердить происхождение/право на регулярное использование.
- Стоковые фото/видео: Pexels — собственные условия сервиса (не CC0!),
  Openverse/Wikimedia — смешанные лицензии (не целиком CC0): при подключении
  адаптера обязательно записывать конкретную лицензию файла и атрибуцию.
- Проверка доступности источника: HEAD-сбой ≠ «мёртв» — выполняется fallback
  GET, источник помечается недоступным в `assets.status` (не удаляется молча).
- Голоса Edge-TTS — неофициальный сервис Microsoft; для продакшена рассмотрите
  Azure Speech (квота F0 500k симв./мес; коммерческие права — paid tier) или
  локальный Piper (MIT). Движок указан в каждом `render_report.json`.

## YouTube: квоты и раскрытие синтетики

- Квота videos.insert — проверяйте фактическое значение в Cloud Console своего
  проекта (см. docs/CLOUD_RESEARCH.md; старую цифру «1600 units» истиной
  не считаем). При 4 загрузках/день запас обычно большой.
- `status.containsSyntheticMedia=true` ставится по умолчанию: озвучка и видеоряд
  создаются ИИ и выглядят реалистично — это критерий раскрытия по правилам
  YouTube. Отключается `YOUTUBE_DISCLOSE_SYNTHETIC=false` только если контент
  не попадает под критерии (решение владельца, с его ответственностью).
- `selfDeclaredMadeForKids=false` по умолчанию; контент не детский.
- `hasCustomThumbnail` НЕ является disclosure-флагом и не используется.
- OAuth: `python -m tubecook.cli oauth-youtube` локально (Desktop-клиент,
  consent в Production, иначе refresh-токен живёт 7 дней).

## Мониторинг

- Уведомления админу в Telegram: сбои рендера, пустые слоты, протухшие новости,
  uncertain-публикации, восстановление после перезапуска.
- `/status` — сводка; `/job <id>` — детали + статусы площадок; `/check <id>` —
  сверка uncertain.
- Лог: `journalctl --user -u tubecook-v4` и `data/tubecook.log`.

## Разрешение боевого запуска (чек-лист владельца)

1. `bash scripts/hp_bench.sh` — замеры VA-API/CPU на HP.
2. `.env`: TUBECOOK_ADMINS/SENDERS (ID), TELEGRAM_BOT_TOKEN,
   TELEGRAM_CHANNEL_ID (проверить права бота в канале @svobodnye_ludi_zp),
   YOUTUBE_CHANNEL_ID.
3. `python -m tubecook.cli oauth-youtube` → token.json на месте.
4. Тестовый выпуск: `/test` → превью лично Сергею → убедиться в качестве.
5. `TUBECOOK_PUBLISH_LIVE=true` → один контролируемый выпуск.
6. Убедиться в работоспособности обеих площадок → (позже, отдельно)
   `TUBECOOK_AUTONOMOUS=true` + `TUBECOOK_REQUIRE_APPROVAL=false` для
   штатного режима 4/день без подтверждений.
