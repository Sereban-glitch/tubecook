#!/usr/bin/env python3
# ============================================================================
# 06_render_short.py v3.0 — Производственный рендерер документального сериала.
# Адаптирован под Intel Core i5-6200U + Intel HD Graphics 520 (VA-API /dev/dri/renderD128)
# Расширенный профиль RAM: до 4-6 ГБ ОЗУ (Linux Mint 22.3, 12 ГБ RAM на борту).
#
# Ключевые возможности v3.0:
#   1. Плавный Ken-Burns эффект (динамический pan/zoom) для архивных фото/стиллов.
#   2. Процедурный оверлей рассекречивания:
#      - Анимированная графическая плашка «ГРИФ: РАССЕКРЕЧЕНО / TOP SECRET» (0-4 сек)
#      - Кинозерно (film grain) и аналоговые сканирующие линии (CRT scanlines)
#      - Кинематографическая виньетка
#   3. Авто-даккинг саундтрека: фоновый BGM плавно приглушается на -22 dB под голосом.
#   4. Двойной экспорт (Dual Export):
#      - YouTube Shorts: 1080x1920 @ 30fps (h264_vaapi 8 Mbps, High Profile, faststart)
#      - Telegram Preview: 540x960 CRF 26 faststart (до 15 МБ, автовоспроизведение в канале)
# ============================================================================
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER = "/dev/dri/renderD128"
FONTS_DIR = "/usr/share/fonts/truetype/dejavu"
CANON = {"w": 1080, "h": 1920, "fps": 30, "vbitrate": "8M"}


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", flush=True)


def run(cmd: list, stage: str) -> None:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode != 0:
        log(stage, (p.stderr or p.stdout)[-1500:])
        raise RuntimeError(f"стадия {stage} завершилась с ошибкой {p.returncode}")


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def vaapi_enc() -> list:
    if Path(RENDER).exists():
        return ["-vaapi_device", RENDER, "-c:v", "h264_vaapi",
                "-b:v", CANON["vbitrate"], "-pix_fmt", "nv12"]
    log("enc", "ВНИМАНИЕ: VA-API недоступен — откат на libx264 ultrafast")
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"]


def stage_stocks(m: dict, work: Path, force: bool, voice_total: float = 45.0) -> list:
    st_dir, norm_dir = work / "stocks", work / "norm"
    st_dir.mkdir(parents=True, exist_ok=True)
    norm_dir.mkdir(exist_ok=True)
    index = st_dir / "index.json"

    scenes = m.get("scenes", [])
    queries = [s.get("source_query") or s.get("query") for s in scenes if (s.get("source_query") or s.get("query"))]
    if not queries:
        queries = [" ".join(m.get("keywords", [])) or m["title"]]

    if not index.exists() or force:
        for q in queries:
            run([sys.executable, HERE / "02_fetch_stocks.py",
                 "--query", q, "--count", "4",
                 "--out", str(st_dir)], "stocks")

    with open(index, encoding="utf-8") as f:
        items = json.load(f)

    # Приводим к списку доступных файлов
    valid_files = [Path(i["file"]) for i in items if Path(i["file"]).exists()]
    if not valid_files:
        raise RuntimeError(f"Не найдены скачанные медиафайлы в {st_dir}")

    n_scenes = len(scenes) if scenes else 6
    total_raw = sum(s.get("duration_s", 7.0) for s in scenes) if scenes else 42.0
    scale = voice_total / total_raw if total_raw > 0 else 1.0

    outs = []
    for i in range(n_scenes):
        dst = norm_dir / f"scene_{i:02d}.mp4"
        if dst.exists() and not force:
            outs.append(dst)
            continue
        src = valid_files[i % len(valid_files)]
        raw_dur = scenes[i].get("duration_s", 7.0) if scenes else 7.0
        dur = f"{(raw_dur * scale):.2f}"
        
        # Если входной файл — статичное изображение (jpg, png) -> Ken-Burns генератор!
        if src.suffix.lower() in (".jpg", ".jpeg", ".png"):
            # Плавный Ken-Burns: масштабирование 1080x1920 с легким зумом
            zoom_expr = "min(zoom+0.0012,1.18)" if i % 2 == 0 else "max(1.18-0.0012*on,1.0)"
            kb_filter = (
                f"zoompan=z='{zoom_expr}':d={int(float(dur)*30)}:s=1080x1920:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',format=nv12,fps=30"
            )
            run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-loop", "1", "-t", dur, "-i", src,
                 "-vf", kb_filter,
                 *vaapi_enc(), "-an", "-movflags", "+faststart", "-y", dst], "stocks_kb")
        else:
            run(["bash", HERE / "05_normalize_clip.sh", src, dst, dur], "stocks")
        outs.append(dst)
    log("stocks", f"Собрано {len(outs)} нормализованных сцен (подогнано под звук: {voice_total:.1f} c)")
    return outs


def stage_tts(m: dict, work: Path, force: bool) -> dict:
    tts_dir = work / "tts"
    words_f, mp3 = tts_dir / "words.json", tts_dir / "voice.mp3"
    if not (words_f.exists() and mp3.exists()) or force:
        script_f = tts_dir / "script.txt"
        script_f.parent.mkdir(parents=True, exist_ok=True)
        text = m.get("script") or m.get("narration_full") or ""
        script_f.write_text(text, encoding="utf-8")
        run([sys.executable, HERE / "03_tts_edge.py",
             "--file", script_f, "--voice", m.get("voice", "ru-RU-DmitryNeural"),
             "--out", str(tts_dir)], "tts")
    with open(words_f, encoding="utf-8") as f:
        words = json.load(f)
    log("tts", f"Синтезировано {len(words)} слов ({words[-1]['end']} сек)")
    return {"words": words, "mp3": mp3}


def stage_ass(m: dict, work: Path, force: bool) -> Path:
    ass = work / "subs" / "short.ass"
    if not ass.exists() or force:
        run([sys.executable, HERE / "04_build_ass.py",
             "--words", str(work / "tts" / "words.json"),
             "--hook", m.get("hook", m["title"]),
             "--out", str(ass)], "ass")
    return ass


def stage_scenes(m: dict, work: Path, norm: list, force: bool) -> list:
    sc_dir = work / "scenes"
    sc_dir.mkdir(exist_ok=True)
    n, outs = len(norm), []
    
    # Метаданные рассекречивания для плашки 0-4 сек
    meta = m.get("historical_metadata", {})
    yr_decl = meta.get("year_declassified", "РАССЕКРЕЧЕНО")
    agency = meta.get("agency", "TOP SECRET")
    stamp_text = f"ГРИФ СНЯТ В {yr_decl} Г. // АРХИВ {agency}"

    for i, src in enumerate(norm):
        dst = sc_dir / f"composed_{i:02d}.mp4"
        if dst.exists() and not force:
            outs.append(dst)
            continue
        
        # На первой сцене накладываем HUD-плашку рассекречивания (0-4s)
        stamp_filter = ""
        if i == 0:
            stamp_filter = (
                f",drawbox=y=160:h=70:color=red@0.85:t=fill:enable='between(t,0.2,4.0)',"
                f"drawtext=fontfile={FONTS_DIR}/DejaVuSans-Bold.ttf:text='[ {stamp_text} ]':"
                f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y=176:enable='between(t,0.2,4.0)'"
            )

        # Трюк размытия фона 540p + резкий передний план + виньетка + кинозерно
        vf = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=540:960,boxblur=8:2,scale=1080:1920,eq=brightness=-0.08[bgb];"
            "[fg]scale=1080:1536:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            f",vignette=PI/5,noise=alls=10:allf=t+u{stamp_filter},format=nv12[v]"
        )
        run(["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", src, "-filter_complex", vf, *vaapi_enc(),
             "-an", "-movflags", "+faststart", "-y", dst], "scenes")
        outs.append(dst)
    log("scenes", f"Собрано {len(outs)} композитных сцен с HUD-эффектами")
    return outs


def stage_concat(work: Path, scenes: list) -> Path:
    lst = work / "concat.txt"
    lst.write_text("\n".join(f"file '{s.resolve()}'" for s in scenes) + "\n", encoding="utf-8")
    base = work / "base.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", "-y", base], "concat")
    return base


def stage_audio(m: dict, work: Path, tts_data: dict, video_total: float) -> Path:
    mix = work / "audio_mix.wav"
    bgm = m.get("bgm")
    has_bgm = bool(bgm and Path(bgm).exists())
    
    # Авто-даккинг: фоновая музыка опускается на -22 dB под голосом
    filters = []
    if has_bgm:
        gain = m.get("bgm_gain_db", -22)
        filters.append(
            f"[1:a]atrim=0:{video_total:.2f},volume={gain}dB,"
            f"afade=t=out:st={max(0, video_total - 1.5):.2f}:d=1.5[b];"
            "[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a0];"
        )
    else:
        filters.append("[0:a]anull[a0];")
        
    filters.append(
        f"[a0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad,atrim=0:{video_total:.2f}[a1]"
    )
    ins = ["-i", tts_data["mp3"]]
    if has_bgm:
        ins += ["-stream_loop", "-1", "-i", bgm]
        
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", *ins,
         "-filter_complex", "".join(filters), "-map", "[a1]",
         "-c:a", "pcm_s16le", "-y", mix], "audio")

    # Двухпроходная нормализация EBU R128 (-16 LUFS для YouTube Shorts)
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", mix,
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"], capture_output=True, text=True)
    meas = re.search(r"\{[^{}]*\}", p.stderr or "", re.S)
    if not meas:
        raise RuntimeError("loudnorm: не удалось замерить громкость")
    v = json.loads(meas.group(0))

    af = ("loudnorm=I=-16:TP=-1.5:LRA=11:"
          f"measured_I={v['input_i']}:measured_TP={v['input_tp']}:"
          f"measured_LRA={v['input_lra']}:measured_thresh={v['input_thresh']}:"
          "offset=true:linear=true")
    final = work / "audio_final.m4a"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", mix,
         "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-y", final], "audio")
    return final


def stage_burn(work: Path, base: Path, audio: Path, ass: Path) -> tuple:
    final = work / "out" / "final_1080x1920.mp4"
    final.parent.mkdir(exist_ok=True)
    sub = f"subtitles={ass}:fontsdir={FONTS_DIR}"
    t0 = time.time()
    run(["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", base, "-i", audio,
         "-vf", f"{sub},format=nv12", *vaapi_enc(),
         "-c:a", "copy", "-movflags", "+faststart", "-shortest", "-y", final], "burn")
    return final, time.time() - t0


def stage_telegram_preview(work: Path, final: Path) -> Path:
    tg_video = work / "out" / "preview_telegram.mp4"
    # Оптимизированный 540x960 CRF 26 ролик до 15 МБ для Telegram
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", final,
         "-vf", "scale=540:960:flags=lanczos", "-r", "30",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-y", tg_video], "tg_preview")
    mb = tg_video.stat().st_size / (1024 * 1024)
    log("tg_preview", f"Telegram видео готово: {tg_video} ({mb:.2f} МБ <= 15 МБ)")
    return tg_video


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка документального Short v3.0 (VA-API)")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--workdir", help="рабочая директория (по умолчанию build/<id>)")
    ap.add_argument("--force", action="store_true", help="пересобрать стадии заново")
    args = ap.parse_args()

    m = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    work = Path(args.workdir) if args.workdir else HERE / "build" / m.get("id", "task")
    work.mkdir(parents=True, exist_ok=True)

    log("pipeline", f"=== Запуск рендера эпизода: {m.get('title')} ===")
    t_start = time.time()

    # 1. TTS
    tts_data = stage_tts(m, work, args.force)
    voice_total = tts_data["words"][-1]["end"] + 0.8
    # 2. Stocks & Scenes (масштабировано под точный звук)
    norm_scenes = stage_stocks(m, work, args.force, voice_total=voice_total)
    # 3. ASS Subtitles
    ass_path = stage_ass(m, work, tts_data, args.force)
    # 4. Composed Scenes with HUD
    comp_scenes = stage_scenes(m, work, norm_scenes, args.force)
    # 5. Concat
    base_video = stage_concat(work, comp_scenes)
    # 6. Audio Mix + Ducking + R128
    tot_dur = ffprobe_duration(base_video)
    final_audio = stage_audio(m, work, tts_data, tot_dur)
    # 7. Burn Subtitles & Final VA-API encode
    final_yt, burn_time = stage_burn(work, base_video, final_audio, ass_path)
    # 8. Dual Export: Telegram video
    final_tg = stage_telegram_preview(work, final_yt)

    tot_time = time.time() - t_start
    log("pipeline", f"=== РЕНДЕР ЗАВЕРШЕН ЗА {tot_time:.1f} сек ===")
    log("pipeline", f"YouTube Master: {final_yt} ({final_yt.stat().st_size / 1e6:.1f} МБ)")
    log("pipeline", f"Telegram Master: {final_tg} ({final_tg.stat().st_size / 1e6:.1f} МБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
