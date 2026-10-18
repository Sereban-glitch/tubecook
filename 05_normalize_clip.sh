#!/usr/bin/env bash
# ============================================================================
# 05_normalize_clip.sh — нормализация одного сток-клипа под канон конвейера.
# Канон (без него Concat Demuxer не работает — Глава 2.3):
#   1080x1920, 30 к/с, h264_vaapi, nv12, GOP 60, ~8 Мбит/с, faststart.
# Фильтр: cover-scale (увеличить по большей стороне) + центр-кроп.
# ВАЖНО: скейл/кроп выполняются на CPU (swscale), а КОДИРОВАНИЕ — на GPU VA-API.
# Это и есть режим «малой RAM»: кадры не копятся в памяти (потоковая обработка).
#
# Использование: ./05_normalize_clip.sh вход.mp4 [выход.mp4] [длительность]
#   длительность (сек, опционально) — обрезает клип под сценарную раскладку.
# ============================================================================
set -euo pipefail

IN="${1:?нужен входной файл}"
OUT="${2:-${IN%.*}_norm.mp4}"
DUR="${3:-}"
RENDER="/dev/dri/renderD128"

# Проверка VA-API с мягкой деградацией на x264 ultrafast (для VPS без GPU)
ENC="-c:v h264_vaapi -b:v 8M"
HW_UP=",format=nv12,hwupload"
HW_DEV="-vaapi_device $RENDER"
if ! ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=64x64:rate=30:duration=0.2 \
     -vaapi_device "$RENDER" -vf "format=nv12,hwupload" -c:v h264_vaapi -y /tmp/_vaapi_probe.mp4 2>/dev/null; then
  echo "[norm] VA-API недоступен — деградация на libx264 ultrafast (медленнее в 3-6 раз)" >&2
  ENC="-c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p"
  HW_UP=""
  HW_DEV=""
fi
rm -f /tmp/_vaapi_probe.mp4

TRIM=()
if [ -n "$DUR" ]; then
  # -ss до входа, -t после: быстрый seek по ключевым кадрам, без перекодирования лишнего
  TRIM=(-ss 0 -t "$DUR")
fi

ffmpeg -hide_banner -loglevel warning -stats \
  "${TRIM[@]}" -i "$IN" \
  $HW_DEV \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30$HW_UP" \
  $ENC -g 60 -profile:v high \
  -an -movflags +faststart -y "$OUT"

# Контроль канона: параметр должны совпасть до бита, иначе concat -c copy выпадет
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,pix_fmt,codec_name \
  -of csv=p=0 "$OUT" | sed 's/^/[norm] канон: /'
echo "[norm] готово: $OUT"
