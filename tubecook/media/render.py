"""Рендер-движок Tubecook v4: сцены -> FFmpeg-граф -> мастер 1080x1920@30.

Ключевые решения (из ТЗ «Качество видео»):
- движение: зум фона (zoompan) + въезд карточки с ease-out + параллакс-слой
  акцентов + кроссфейды xfade. Ken Burns — только один из приёмов, не основа;
- финальная фраза не обрывается: длительность = конец речи + tail (0.9 c),
  хвост добавляется tpad=stop_mode=clone, -shortest ЗАПРЕЩЁН (assert в коде);
- аудио: BGM с даккингом sidechaincompress от голоса, двухпроходный loudnorm
  (EBU R128, -16 LUFS), фейд без обрезания последнего слова;
- после кодирования всё проверяется ffprobe (длительности/битность) —
  не только exit code.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from tubecook.media import ass as assm
from tubecook.media import ffmpeg_utils as ff
from tubecook.media import gfx, scenes as scenesm
from tubecook.media.tts import synthesize

XF_TRANSITIONS = ["fade", "smoothleft", "circleopen"]


def render_episode(payload: dict, cfg, work_dir: Path, profile: str = "base",
                   engine: str = "auto", channel: str = "Свободные люди Запорожья") -> dict:
    """Полный рендер выпуска. Возвращает артефакты + честный отчёт."""
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    stages: dict = {}

    # 1) озвучка (edge-tts или мок; движок попадает в отчёт)
    t0 = time.time()
    tts = synthesize(payload.get("script", ""), cfg, work / "tts", engine=engine)
    stages["tts"] = round(time.time() - t0, 1)
    words = tts.words
    speech_end = tts.speech_end

    # 2) сцены + графика (РАНЬШЕ субтитров: границы предложений общие)
    t0 = time.time()
    scene_dir = work / "scenes"
    sc_list = scenesm.build_scenes(payload, words, speech_end,
                                   out_dir=str(scene_dir), channel=channel)
    layers = []
    for sc in sc_list:
        layers.append(gfx.render_scene_layers(sc.to_dict(),
                                               cfg_font_bold=cfg.font_bold,
                                               cfg_font_reg=cfg.font_regular))
    stages["gfx"] = round(time.time() - t0, 1)

    # 3) хронометраж: video = речь + tail; -shortest под запретом
    tail = cfg.render.tail_s
    total = round(speech_end + tail, 3)

    # 4) караоке-субтитры: границы предложений = границы сцен,
    #    строки-ряды без переносов + motion-слои (кинетика, бейджи, прогресс)
    t0 = time.time()
    spans = scenesm.sentence_word_spans(payload.get("script", ""), words)
    ass_path = assm.build_ass(words, payload.get("hook", ""), work / "subs.ass",
                              font=cfg.sub_font, sentence_spans=spans,
                              scenes=sc_list, total=total,
                              font_bold_path=cfg.font_bold)
    stages["ass"] = round(time.time() - t0, 1)

    # 5) аудио: даккинг + R128 (двухпроходный), точная длина total
    t0 = time.time()
    audio_path = _render_audio(tts.path, cfg.bgm_path, total, work,
                               bgm_volume=cfg.bgm_volume)
    stages["audio"] = round(time.time() - t0, 1)

    # 6) видео-граф + энкод + мукс
    t0 = time.time()
    master = _render_video(layers, sc_list, total, ass_path, audio_path,
                           work, cfg, profile)
    stages["video"] = round(time.time() - t0, 1)

    # 7) честная проверка финала (не только exit code)
    vdur = ff.probe_duration(master)
    adur = ff.probe_duration(audio_path)
    ff.assert_tail(vdur, adur, speech_end, tail)

    report = {
        "profile": profile,
        "tts_engine": tts.engine,
        "voice": cfg.voice,
        "speech_end_s": round(speech_end, 2),
        "total_s": round(vdur, 2),
        "audio_s": round(adur, 2),
        "tail_s": tail,
        "scenes": [{"kind": sc.kind, "dur": round(sc.dur, 2)} for sc in sc_list],
        "stages_s": stages,
        "wall_s": round(time.time() - t_start, 1),
        "master_mb": round(ff.size_mb(master), 2),
        "hw": "vaapi" if "h264_vaapi" in " ".join(cfg.render.encoder()) else "cpu",
        "bgm": {"category": getattr(cfg, "bgm_category", "custom"),
                "track": str(cfg.bgm_path) if cfg.bgm_path else None,
                "volume": getattr(cfg, "bgm_volume", 0.5)},
        "env": ff.env_report(),
        "fonts": {"bold": cfg.font_bold, "regular": cfg.font_regular},
    }
    (work / "render_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"master": master, "ass": ass_path, "words": words, "report": report}


# ------------------------------------------------------------------ аудио

def _render_audio(voice_path, bgm_path, total: float, work: Path,
                  bgm_volume: float = 0.5) -> Path:
    """Голос + BGM(даккинг) + loudnorm(R128) -> audio_final.m4a длиной total.

    Баланс (обратная связь владельца): голос — кристально чистый, музыка —
    лёгким фоном. Поэтому: (1) BGM получает highpass=180 — не мутит частоты
    диктора; (2) bed-громкость задаётся bgm_volume (треки нормализованы
    к пику -12 dBFS); (3) sidechaincompress прижимает музыку на ~12+ dB
    во время речи (attack 8 мс — ныряет сразу, release 280 мс — мягко
    всплывает в паузах); (4) amix normalize=0 — голос не ослабляется.
    """
    has_bgm = Path(bgm_path).exists() if bgm_path else False

    def graph(loud: str) -> str:
        parts = [
            # голос: к 48k стерео, пад до total (чистый путь без фильтров)
            f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"apad=whole_dur={total:.3f}[va]",
        ]
        if has_bgm:
            parts += [
                # подложка: срез низа + мягкий въезд + bed-громкость
                f"[1:a]aresample=48000,highpass=f=180,volume={max(0.0, bgm_volume):.3f},"
                f"afade=t=in:st=0:d=1.0[bg]",
                f"[va]asplit=2[va1][va2]",
                # даккинг: музыка ныряет под голос (лёгкий фон, не тишина)
                f"[bg][va1]sidechaincompress=threshold=0.02:ratio=12:attack=8:"
                f"release=280[bgo]",
                f"[bgo][va2]amix=inputs=2:duration=first:normalize=0[m]",
                f"[m]{loud}[aout]",
            ]
        else:
            parts += [f"[va]{loud}[aout]"]
        return ";".join(parts)

    out = work / "audio_final.m4a"
    inputs = ["-i", str(voice_path)]
    if has_bgm:
        inputs = ["-i", str(voice_path), "-stream_loop", "-1", "-t",
                  f"{total:.3f}", "-i", str(bgm_path)]

    # проход 1: замер громкости
    meas = "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json"
    p = _run_ffmpeg(inputs + ["-filter_complex", graph(meas), "-map", "[aout]",
                              "-f", "null", "-"], "audio_measure")
    m = re.search(r"\{[^{}]*\}", p.stderr or "", re.S)
    if not m:
        raise ff.FFError("loudnorm: не удалось снять замер громкости")
    v = json.loads(m.group(0))
    # тихий/немой вход (мок-TTS в тестах) даёт -inf: двухпроходный режим
    # неприменим — честно переходим на однопроходный loudnorm
    try:
        _finite = all(_is_finite(v.get(k)) for k in
                      ("input_i", "input_tp", "input_lra", "input_thresh"))
    except (TypeError, ValueError):
        _finite = False
    if _finite:
        try:
            target_offset = float(v.get("target_offset") or 0.0)
        except (TypeError, ValueError):
            target_offset = 0.0
        af = ("loudnorm=I=-16:TP=-1.5:LRA=11:"
              f"measured_I={v['input_i']}:measured_TP={v['input_tp']}:"
              f"measured_LRA={v['input_lra']}:measured_thresh={v['input_thresh']}:"
              f"offset={target_offset:.3f}:linear=true")
    else:
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
    af += f",afade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8"
    af += f",atrim=0:{total:.3f}"

    # проход 2: нормализация + фейд
    _run_ffmpeg(inputs + ["-filter_complex", graph(af), "-map", "[aout]",
                          "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                          "-y", str(out)], "audio_final")
    return out


def _is_finite(x) -> bool:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f not in (float("inf"), float("-inf")) and f == f


def _run_ffmpeg(args: list, stage: str):
    cmd = ["ffmpeg", "-hide_banner", "-nostdin"] + [str(a) for a in args]
    ff.assert_no_shortest(cmd)
    import subprocess
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise ff.FFError(f"[{stage}] exit={p.returncode}: "
                         f"{(p.stderr or p.stdout)[-2000:]}")
    return p


# ------------------------------------------------------------------ видео

def _scene_filter_graph(dur: float, frames: int, W: int, H: int, fps: int,
                        zamp: float, slide_t: float, slide_off: int,
                        direction: int, accx: str, accy: str,
                        first: bool, last: bool) -> list:
    """FFmpeg-граф ТЕЛА сцены (без хвостов переходов; тестируемая функция).

    Правило «без просвечивания текста» (обратная связь владельца):
    переходы собираются отдельно из фоновых клипов БЕЗ карточек
    (см. _bgonly_filter_graph/_transition_cmd), поэтому в окно кроссфейда
    карточных слоёв нет вообще. В теле сцены карточка дополнительно
    гаснет к его концу (кроме финальной сцены — там карта живёт до
    стоп-кадра tpad).
    """
    if first:
        fin_st, fin_d = 0.22, 0.40          # первая сцена: лёгкая задержка
    else:
        fin_st, fin_d = 0.10, 0.30          # сразу после перехода
    parts = [
        # фон: лёгкий апскейл для субпиксельного зума -> плавный zoompan
        f"[0:v]scale=1350:2400:force_original_aspect_ratio=increase,"
        f"crop=1350:2400,zoompan=z='min(1.0+{zamp}*on/{frames},1.0+{zamp})'"
        f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={fps}[bgz]",
        # карточка: въезд после перехода, гашение к концу тела (не last)
    ]
    if last:
        parts.append(
            f"[1:v]format=rgba,fade=t=in:st={fin_st:.3f}:d={fin_d:.3f}:alpha=1[card]")
    else:
        fout_st = max(0.0, dur - 0.37)
        parts.append(
            f"[1:v]format=rgba,fade=t=in:st={fin_st:.3f}:d={fin_d:.3f}:alpha=1,"
            f"fade=t=out:st={fout_st:.3f}:d=0.35:alpha=1[card]")
    parts += [
        f"[2:v]format=rgba[acc]",
        f"[bgz][card]overlay=x='if(lt(t,{slide_t}),{direction * slide_off}*"
        f"pow(1-min(t/{slide_t},1),2),0)':y=0[ovc]",
        f"[ovc][acc]overlay=x='{accx}':y='{accy}'[sc]",
        f"[sc]format=yuv420p,fps={fps},setsar=1[v]",
    ]
    return parts


def _bgonly_filter_graph(frames: int, W: int, H: int, fps: int, zamp: float,
                         accx: str, accy: str) -> list:
    """Клип «фон без карточки» для переходов: зум + параллакс акцентов.

    Именно из таких клипов собираются кроссфейды — в них нет текста,
    поэтому уходящая карточка физически не может просвечивать сквозь
    входящую. Память клипа копеечная (короткий, один слой).
    """
    return [
        f"[0:v]scale=1350:2400:force_original_aspect_ratio=increase,"
        f"crop=1350:2400,zoompan=z='min(1.0+{zamp}*on/{frames},1.0+{zamp})'"
        f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={fps}[bgz]",
        f"[1:v]format=rgba[acc]",
        f"[bgz][acc]overlay=x='{accx}':y='{accy}'[sc]",
        f"[sc]format=yuv420p,fps={fps},setsar=1[v]",
    ]


def _transition_cmd(bg_a: Path, bg_b: Path, out: Path, style: str,
                    t_eff: float, fps: int) -> list:
    """Команда кроссфейда двух фоновых клипов (2 коротких входа, ~0 RAM)."""
    graph = (f"[0:v]fps={fps},setsar=1[a];[1:v]fps={fps},setsar=1[b];"
             f"[a][b]xfade=transition={style}:duration={t_eff:.4f}:offset=0[v]")
    return ["ffmpeg", "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-filter_complex_threads", "1", "-i", str(bg_a), "-i", str(bg_b),
            "-filter_complex", graph, "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-pix_fmt", "yuv420p", str(out)]


def _render_video(layers: list, sc_list, total: float, ass_path: Path,
                  audio_path: Path, work: Path, cfg, profile: str,
                  force: bool = False) -> Path:
    """Трёхпроходная сборка с жёстким лимитом памяти (пик <= ~0.5 ГБ).

    Прежняя однопроходная xfade-цепочка на N входов держала очередь
    кадров всех сцен и на 12 сценах съедала ~1.8 ГБ. Новая схема:

    1) тело каждой сцены (body_i) кодируется отдельно, КАК РАНЬШЕ
       (зум + карточка + параллакс), но без хвостов переходов;
    2) для каждой сцены кодируется короткий фоновый клип bgnone_i
       (БЕЗ карточки) длиной в кадр перехода; кроссфейды trans_i
       собираются попарно из двух таких клипов — в переходах нет
       текста -> просвечивание исключено по построению;
    3) финальный проход: concat-demuxer по телам и переходам
       (без декодирования, copy) + субтитры + tpad-хвост + фейд +
       энкод (VA-API/CPU) + мукс. В финале ровно ОДИН видео-вход.

    Длительности кратны кадрам: переходы не рассинхронизируются.
    -shortest по-прежнему запрещён (assert ниже).
    """
    fps = cfg.render.fps
    W, H = cfg.render.w, cfg.render.h
    extended = profile == "extended"
    T = cfg.render.extended_transition_s if extended else cfg.render.transition_s
    zamp = 0.07 if extended else 0.04
    slide_t = 0.55
    slide_off = 240 if extended else 170
    n = len(layers)
    t_frames = max(1, int(round(T * fps)))
    t_eff = t_frames / fps            # кадрово-точная длительность перехода

    def _skip(dst: Path) -> bool:
        return dst.exists() and dst.stat().st_size > 0 and not force

    # ---------------- этап 1: тела сцен + фоновые клипы переходов
    body_files: list = []
    for i, (lay, sc) in enumerate(zip(layers, sc_list)):
        F = max(2, int(round(sc.dur * fps)))
        head_f = 0 if i == 0 else t_frames
        tail_f = 0 if i == n - 1 else t_frames
        body_frames = max(2, F - head_f - tail_f)
        body_dur = body_frames / fps
        direction = -1 if i % 2 == 0 else 1
        if extended:
            accx = "(W-w)/2+26*sin(2*PI*t/9)"
            accy = "(H-h)/2+42*sin(2*PI*t/13)"
        else:
            accx, accy = "(W-w)/2", "(H-h)/2"

        body = work / f"body_{i:02d}.mp4"
        body_files.append(body)
        if not _skip(body):
            graph = _scene_filter_graph(body_dur, body_frames, W, H, fps,
                                        zamp, slide_t, slide_off, direction,
                                        accx, accy, first=(i == 0),
                                        last=(i == n - 1))
            cmd = ["ffmpeg", "-y", "-hide_banner", "-nostdin",
                   "-loglevel", "error", "-filter_complex_threads", "1",
                   "-loop", "1", "-framerate", str(fps), "-t", f"{body_dur:.4f}",
                   "-i", str(lay["bg"]),
                   "-loop", "1", "-framerate", str(fps), "-t", f"{body_dur:.4f}",
                   "-i", str(lay["card"]),
                   "-loop", "1", "-framerate", str(fps), "-t", f"{body_dur:.4f}",
                   "-i", str(lay["accent"])]
            cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(body)]
            ff.run(cmd, f"body_{i:02d}", cwd=str(work))

        # фоновый клип для переходов (без карточки) — нужен всем, кроме
        # головы первой сцены и хвоста последней (не участвуют в xfade)
        need_bg = (i < n - 1) or (i > 0)
        if need_bg:
            bgonly = work / f"bgnone_{i:02d}.mp4"
            if not _skip(bgonly):
                graph = _bgonly_filter_graph(t_frames, W, H, fps, zamp,
                                             accx, accy)
                cmd = ["ffmpeg", "-y", "-hide_banner", "-nostdin",
                       "-loglevel", "error", "-filter_complex_threads", "1",
                       "-loop", "1", "-framerate", str(fps), "-t", f"{t_eff:.4f}",
                       "-i", str(lay["bg"]),
                       "-loop", "1", "-framerate", str(fps), "-t", f"{t_eff:.4f}",
                       "-i", str(lay["accent"])]
                cmd += ["-filter_complex", ";".join(graph), "-map", "[v]",
                        "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "16", "-pix_fmt", "yuv420p", str(bgonly)]
                ff.run(cmd, f"bgnone_{i:02d}", cwd=str(work))

    # ---------------- этап 1b: короткие кроссфейды (2 входа, ~0 RAM)
    if n > 1:
        for i in range(n - 1):
            trans = work / f"trans_{i:02d}.mp4"
            if _skip(trans):
                continue
            cmd = _transition_cmd(work / f"bgnone_{i:02d}.mp4",
                                  work / f"bgnone_{i + 1:02d}.mp4",
                                  trans, XF_TRANSITIONS[(i + 1) % len(XF_TRANSITIONS)],
                                  t_eff, fps)
            ff.run(cmd, f"trans_{i:02d}", cwd=str(work))

    # ---------------- этап 2: concat-demuxer (copy) + субтитры + энкод
    # порядок: body_0, trans_0, body_1, trans_1, ..., body_{n-1}
    concat_list = work / "concat.txt"
    lines = [f"file '{(body_files[0]).name}'"]
    for i in range(n - 1):
        lines.append(f"file '{(work / f'trans_{i:02d}.mp4').name}'")
        lines.append(f"file '{(body_files[i + 1]).name}'")
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # длительность склейки (кадрово-точная) для tpad
    S = sum(max(2, int(round(sc.dur * fps))) -
            (0 if k == 0 else t_frames) -
            (0 if k == n - 1 else t_frames) for k, sc in enumerate(sc_list))
    S = S / fps + (n - 1) * t_eff
    pad = max(0.0, round(total - S, 3)) + 0.02

    enc = cfg.render.encoder()
    cmd: list = ["ffmpeg", "-y", "-hide_banner", "-nostdin",
                 "-loglevel", "error", "-filter_complex_threads", "1"]
    if enc and enc[0] == "-vaapi_device":
        cmd += ["-vaapi_device", enc[1]]
        enc_codec = enc[2:]
    else:
        enc_codec = enc

    fmt = "format=nv12,hwupload" if (enc and "h264_vaapi" in " ".join(enc)) \
        else "format=yuv420p"
    fonts_dir = str(Path(cfg.font_bold).parent)
    cmd += ["-f", "concat", "-safe", "0", "-i", concat_list.name,
            "-i", str(audio_path)]
    graph = [
        f"[0:v]subtitles=filename=subs.ass:fontsdir={fonts_dir},"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f},"
        f"fade=t=out:st={max(0.0, total - 0.7):.3f}:d=0.7,{fmt}[vout]"
    ]
    cmd += ["-filter_complex", ";".join(graph),
            "-map", "[vout]", "-map", "1:a"]
    cmd += [str(c) for c in enc_codec]
    cmd += ["-r", str(fps), "-c:a", "copy", "-movflags", "+faststart",
            str(work / "master.mp4")]
    ff.assert_no_shortest(cmd)

    ff.run(cmd, "video_render", cwd=str(work))
    return work / "master.mp4"
