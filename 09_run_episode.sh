#!/usr/bin/env bash
# ============================================================================
# 09_run_episode.sh — Полный оркестратор выпуска одной серии документального цикла.
# Спроектирован под аппаратный профиль:
#   Intel Core i5-6200U (2C/4T Skylake) + Intel HD Graphics 520 (VA-API)
#   12 ГБ RAM (до 4-6 ГБ под рендер) + Linux Mint 22.3
#
# Использование:
#   ./09_run_episode.sh jobs/ep01_midnight_climax.json [--upload-yt] [--post-tg]
# ============================================================================
set -euo pipefail

MANIFEST="${1:?Укажите путь к манифесту серии (напр. jobs/ep01_midnight_climax.json)}"
UPLOAD_YT=false
POST_TG=false

for arg in "$@"; do
  case "$arg" in
    --upload-yt) UPLOAD_YT=true ;;
    --post-tg)   POST_TG=true ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
  set -a; source .env; set +a
fi

echo "===================================================================="
echo " [tubecook] ЗАПУСК ПРОИЗВОДСТВА СЕРИИ: $MANIFEST"
echo " Время старта: $(date)"
echo " Аппаратный профиль: Intel HD Graphics 520 (VA-API /dev/dri/renderD128)"
echo "===================================================================="

# 0. Валидация окружения
command -v ffmpeg >/dev/null || { echo "ОШИБКА: ffmpeg не установлен"; exit 1; }
command -v python3 >/dev/null || { echo "ОШИБКА: python3 не установлен"; exit 1; }

EP_ID=$(python3 -c "import json, sys; print(json.load(open('$MANIFEST')).get('id', 'ep'))")
WORK_DIR="$SCRIPT_DIR/build/$EP_ID"
mkdir -p "$WORK_DIR"

# 1. Запуск v3 рендера Short (Ken-Burns + HUD + VA-API + Ducking + Dual Output)
echo "--> [1/4] Рендер видеоконвейера (v3.0)..."
python3 06_render_short.py --manifest "$MANIFEST" --workdir "$WORK_DIR"

YT_VIDEO="$WORK_DIR/out/final_1080x1920.mp4"
TG_VIDEO="$WORK_DIR/out/preview_telegram.mp4"

if [ ! -f "$YT_VIDEO" ] || [ ! -f "$TG_VIDEO" ]; then
  echo "ОШИБКА: Рендер не создал выходные видеофайлы!"
  exit 2
fi

echo "--> Видео готовы:"
echo "    YouTube:  $YT_VIDEO ($(du -h "$YT_VIDEO" | cut -f1))"
echo "    Telegram: $TG_VIDEO ($(du -h "$TG_VIDEO" | cut -f1))"

# 2. Выгрузка в YouTube Shorts (опционально)
if [ "$UPLOAD_YT" = true ]; then
  echo "--> [2/4] Выгрузка на YouTube Shorts (с disclosure о синтетических медиа)..."
  TITLE=$(python3 -c "import json; print(json.load(open('$MANIFEST')).get('title'))")
  python3 07_upload_youtube.py --video "$YT_VIDEO" --title "$TITLE" --privacy public
else
  echo "--> [2/4] Пропуск выгрузки на YouTube (флаг --upload-yt не передан)"
fi

# 3. Публикация в Telegram канал (опционально)
if [ "$POST_TG" = true ]; then
  echo "--> [3/4] Публикация в Telegram канал (Видео + Досье + Опрос)..."
  python3 08_post_telegram.py --manifest "$MANIFEST" --video "$TG_VIDEO"
else
  echo "--> [3/4] Пропуск публикации в Telegram (флаг --post-tg не передан)"
fi

echo "===================================================================="
echo " [tubecook] СЕРИЯ УСПЕШНО ЗАВЕРШЕНА!"
echo " Готовые материалы: $WORK_DIR/out/"
echo "===================================================================="
