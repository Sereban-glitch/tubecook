#!/usr/bin/env bash
# ============================================================================
# 01_bench_vaapi.sh — бенчмарк аппаратного ускорения Intel HD Graphics 520
# Цель: снять ФАКТИЧЕСКИЕ цифры на вашем ноутбуке до запуска конвейера.
# Результат: таблица в stdout + файл bench/report.json (для Главы 2 руководства).
#
# Использование: ./01_bench_vaapi.sh [длительность_сек]  (по умолчанию 10)
# Зависимости: ffmpeg (сборка с --enable-vaapi), vainfo (пакет vainfo)
# ============================================================================
set -euo pipefail

DUR="${1:-10}"
OUT_DIR="$(dirname "$0")/bench"
RENDER="/dev/dri/renderD128"   # устройство VA-API Intel HD 520
mkdir -p "$OUT_DIR"
REPORT="$OUT_DIR/report.json"

# --- 0. Проверки окружения -------------------------------------------------
echo "== [0] Проверка окружения =="
command -v ffmpeg >/dev/null || { echo "ОШИБКА: ffmpeg не найден"; exit 1; }
command -v vainfo >/dev/null || { echo "ОШИБКА: vainfo не найден (apt install vainfo)"; exit 1; }
[ -e "$RENDER" ] || { echo "ОШИБКА: $RENDER не существует"; exit 1; }

echo "-- VA-API драйвер и кодеки (ищите H.264 Enc / HEVC Enc):"
vainfo --display drm --device "$RENDER" 2>/dev/null | sed -n '1,30p' | tee "$OUT_DIR/vainfo.txt"

FFVER="$(ffmpeg -hide_banner -version | head -n1)"
echo "-- $FFVER"

# --- 1. Синтетический прогон: h264_vaapi 1080x1920@30 (формат Shorts) ------
echo "== [1] h264_vaapi 1080x1920@30, ${DUR}s =="
T0=$(date +%s.%N)
ffmpeg -hide_banner -loglevel error \
  -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=${DUR}" \
  -vaapi_device "$RENDER" \
  -vf "format=nv12,hwupload" \
  -c:v h264_vaapi -b:v 8M -g 60 \
  -y "$OUT_DIR/vaapi_1080x1920.mp4"
T1=$(date +%s.%N)
VAAPI_TIME=$(echo "$T1 - $T0" | bc)
VAAPI_BENCH=$(ffmpeg -hide_banner -benchmark -i "$OUT_DIR/vaapi_1080x1920.mp4" -f null - 2>&1 | grep 'bench: utime' | tail -n1)

# --- 2. Контроль: программный x264 ultrafast (те же параметры) -------------
echo "== [2] x264 ultrafast (контроль, тот же поток) =="
T0=$(date +%s.%N)
ffmpeg -hide_banner -loglevel error -threads "$(nproc)" \
  -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=${DUR}" \
  -c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p -y "$OUT_DIR/x264_1080x1920.mp4"
T1=$(date +%s.%N)
X264_TIME=$(echo "$T1 - $T0" | bc)

# --- 3. Размытие фона: честный boxblur против приёма «blur на пониженном» --
echo "== [3] Трюк размытия фона: 540x960 -> blur -> upscale =="
T0=$(date +%s.%N)
ffmpeg -hide_banner -loglevel error \
  -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=${DUR}" \
  -vaapi_device "$RENDER" \
  -vf "scale=540:960,boxblur=8:2,scale=1080:1920,format=nv12,hwupload" \
  -c:v h264_vaapi -b:v 8M -y "$OUT_DIR/bg_blur_trick.mp4"
T1=$(date +%s.%N)
BLUR_TIME=$(echo "$T1 - $T0" | bc)

# --- 4. Пиковая память процесса (по /usr/bin/time) ------------------------
MEM_PEAK="н/д"
if command -v /usr/bin/time >/dev/null; then
  /usr/bin/time -v ffmpeg -hide_banner -loglevel error \
    -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=${DUR}" \
    -vaapi_device "$RENDER" \
    -vf "format=nv12,hwupload" \
    -c:v h264_vaapi -b:v 8M \
    -y "$OUT_DIR/mem_probe.mp4" 2>"$OUT_DIR/time.txt" || true
  MEM_PEAK=$(grep -i 'Maximum resident' "$OUT_DIR/time.txt" | grep -o '[0-9]*' || echo "н/д")
fi

# --- 5. Свободные ресурсы (RAM/zram/диск) ----------------------------------
RAM_TOTAL=$(free -m | awk 'NR==2{print $2}')
RAM_AVAIL=$(free -m | awk 'NR==2{print $7}')
ZRAM=$(swapon --show --noheadings 2>/dev/null | awk '$3=="zram"{s+=$4} END{print s+0}')
DISK_AVAIL_GB=$(df -BG --output=avail "$(dirname "$0")" | tail -n1 | tr -dc '0-9')

# --- 6. Отчёт ---------------------------------------------------------------
cat <<EOF

================= БЕНЧМАРК VA-API (Intel HD 520) =================
Кодек/тест                       Время wall-clock
----------------------------------------------------------
h264_vaapi 1080x1920@30 ${DUR}s    : ${VAAPI_TIME}s   ($VAAPI_BENCH)
libx264 ultrafast (контроль)      : ${X264_TIME}s
Фон boxblur (трюк 540p)           : ${BLUR_TIME}s
Пиковая память рендера            : ${MEM_PEAK} КБ
RAM всего/свободно, МБ            : ${RAM_TOTAL}/${RAM_AVAIL}
zram, МБ                          : ${ZRAM}
Свободно на диске, ГБ             : ${DISK_AVAIL_GB}
===================================================================
Эмпирическое правило: VA-API быстрее x264-ultrafast в 3-6 раз.
Если нет — смотрите Главу 2.3 руководства (проверьте i965/iHD, занятость GPU).
EOF

cat > "$REPORT" <<EOF
{
  "ffmpeg": "$FFVER",
  "duration_s": $DUR,
  "vaapi_wall_s": $VAAPI_TIME,
  "x264_ultrafast_wall_s": $X264_TIME,
  "bg_blur_trick_wall_s": $BLUR_TIME,
  "mem_peak_kb": "$MEM_PEAK",
  "ram_total_mb": $RAM_TOTAL,
  "ram_avail_mb": $RAM_AVAIL,
  "zram_mb": $ZRAM,
  "disk_avail_gb": $DISK_AVAIL_GB
}
EOF
echo "Отчёт: $REPORT"
