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

    # 2) караоке-субтитры по фактическим таймингам
    t0 = time.time()
    ass_path = assm.build_ass(words, payload.get("hook", ""), work / "subs.ass",
                              font=cfg.sub_font)
    stages["ass"] = round(time.time() - t0, 1)

    # 3) сцены + графика
    t0 = time.time()
    scene_dir = work / "scenes"
    sc_list = scenesm.build_scenes(payload, words, speech_end,
                                   out_dir=str(scene_dir), channel=channel)
    layers = []
    for sc in sc_list:
        layers.append(gfx.render_scene_layers(sc.to_dict()))
    stages["gfx"] = round(time.time() - t0, 1)

    # 4) хронометраж: video = речь + tail; -shortest под запретом
    tail = cfg.render.tail_s
    total = round(speech_end + tail, 3)

    # 5) аудио: даккинг + R128 (двухпроходный), точная длина total
    t0 = time.time()
    audio_path = _render_audio(tts.path, cfg.bgm_path, total, work)
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
        "env": ff.env_report(),
        "fonts": {"bold": cfg.font_bold, "regular": cfg.font_regular},
    }
    (work / "render_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"master": master, "ass": ass_path, "words": words, "report": report}


# ------------------------------------------------------------------ аудио

def _render_audio(voice_path, bgm_path, total: float, work: Path) -> Path:
    """Голос + BGM(даккинг) + loudnorm(R128) -> audio_final.m4a длиной total."""
    has_bgm = Path(bgm_path).exists() if bgm_path else False

    def graph(loud: str) -> str:
        parts = [
            # голос: к 48k стерео, пад до total
            f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"apad=whole_dur={total:.3f}[va]",
        ]
        if has_bgm:
            parts += [
                f"[1:a]volume=0.16,afade=t=in:st=0:d=1.0[bg]",
                f"[va]asplit=2[va1][va2]",
                # даккинг: музыка прижимается голосом
                f"[bg][va1]sidechaincompress=threshold=0.03:ratio=10:attack=10:"
                f"release=350[bgo]",
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

def _render_video(layers: list, sc_list, total: float, ass_path: Path,
                  audio_path: Path, work: Path, cfg, profile: str,
                  force: bool = False) -> Path:
    """Двухстадийный рендер (память и resume):

    1) каждая сцена кодируется отдельно (3 входа-PNG, движение: зум фона +
       въезд карточки + параллакс-слой) -> scene_NN.mp4;
    2) сборка: xfade-цепочка + субтитры + tpad-хвост + фейд + финальный
       энкод (VA-API/CPU) + мукс звука. -shortest запрещён (assert выше).
    """
    fps = cfg.render.fps
    W, H = cfg.render.w, cfg.render.h
    extended = profile == "extended"
    T = cfg.render.extended_transition_s if extended else cfg.render.transition_s
    zamp = 0.07 if extended else 0.04
    fade_in = 0.4 if extended else 0.45
    slide_t = 0.55
    slide_off = 240 if extended else 170
    n = len(layers)

    # ---------------- этап 1: сцены (по одной — экономия RAM, resume по файлам)
    scene_files: list = []
    for i, (lay, sc) in enumerate(zip(layers, sc_list)):
        dst = work / f"scene_{i:02d}.mp4"
        scene_files.append(dst)
        if dst.exists() and dst.stat().st_size > 0 and not force:
            continue
        dur = sc.dur
        frames = max(2, int(round(dur * fps)))
        direction = -1 if i % 2 == 0 else 1
        if extended:
            accx = "(W-w)/2+26*sin(2*PI*t/9)"
            accy = "(H-h)/2+42*sin(2*PI*t/13)"
        else:
            accx, accy = "(W-w)/2", "(H-h)/2"
        graph = [
            # фон: лёгкий апскейл для субпиксельного зума -> плавный zoompan
            f"[0:v]scale=1350:2400:force_original_aspect_ratio=increase,"
            f"crop=1350:2400,zoompan=z='min(1.0+{zamp}*on/{frames},1.0+{zamp})'"
            f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={fps}[bgz]",
            f"[1:v]format=rgba,fade=t=in:st=0:d={fade_in}:alpha=1[card]",
            f"[2:v]format=rgba[acc]",
            f"[bgz][card]overlay=x='if(lt(t,{slide_t}),{direction * slide_off}*"
            f"pow(1-min(t/{slide_t},1),2),0)':y=0[ovc]",
            f"[ovc][acc]overlay=x='{accx}':y='{accy}'[sc]",
            f"[sc]format=yuv420p,fps={fps},setsar=1[v]",
        ]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
               "-filter_complex_threads", "1"]
        for key in ("bg", "card", "accent"):
            cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}",
                    "-i", str(lay[key])]
        cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                "-pix_fmt", "yuv420p", str(dst)]
        ff.run(cmd, f"scene_{i:02d}", cwd=str(work))

    # ---------------- этап 2: сборка
    cmd: list = ["ffmpeg", "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                 "-filter_complex_threads", "1"]
    enc = cfg.render.encoder()
    if enc and enc[0] == "-vaapi_device":
        cmd += ["-vaapi_device", enc[1]]
        enc_codec = enc[2:]
    else:
        enc_codec = enc

    graph: list = []
    for i, sf in enumerate(scene_files):
        cmd += ["-i", str(sf)]
        graph.append(f"[{i}:v]fps={fps},setsar=1[v{i}]")

    if n == 1:
        chain = "[v0]"
    else:
        acc = "[v0]"
        length = sc_list[0].dur
        for i in range(1, n):
            trans = XF_TRANSITIONS[i % len(XF_TRANSITIONS)]
            out_label = f"[x{i}]" if i < n - 1 else "[xv]"
            offset = max(0.0, length - T)
            graph.append(f"{acc}[v{i}]xfade=transition={trans}:duration={T}:"
                         f"offset={offset:.3f}{out_label}")
            length = length + sc_list[i].dur - T
            acc = out_label
        chain = "[xv]"

    # хвост: стоп-кадр + фейд (замена запрещённого -shortest)
    S = sum(sc.dur for sc in sc_list) - T * (n - 1) if n > 1 else sc_list[0].dur
    pad = max(0.0, round(total - S, 3)) + 0.02
    fmt = "format=nv12,hwupload" if (enc and "h264_vaapi" in " ".join(enc)) \
        else "format=yuv420p"
    fonts_dir = str(Path(cfg.font_bold).parent)
    graph.append(
        f"{chain}subtitles=filename=subs.ass:fontsdir={fonts_dir},"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f},"
        f"fade=t=out:st={max(0.0, total - 0.7):.3f}:d=0.7,{fmt}[vout]")

    a_idx = n
    cmd += ["-i", str(audio_path)]
    cmd += ["-filter_complex", ";".join(graph),
            "-map", "[vout]", "-map", f"{a_idx}:a"]
    cmd += [str(c) for c in enc_codec]
    cmd += ["-r", str(fps), "-c:a", "copy", "-movflags", "+faststart",
            str(work / "master.mp4")]
    ff.assert_no_shortest(cmd)

    res = ff.run(cmd, "video_render", cwd=str(work))
    print(res)
    return work / "master.mp4"
