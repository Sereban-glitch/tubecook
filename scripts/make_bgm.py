#!/usr/bin/env python3
"""Генератор нейтральной новостной подложки Tubecook v4.

Заменяет мрачный soft_loop.mp3: три категории, детерминированный синтез
(numpy, без случайности — одинаковый результат на любой машине).

Категории:
- news  — деловой ambient: тёплый пад A-мажор (I-vi-IV-V), лёгкий арп-пульс
          восьмыми, мягкий низкий пульс на 1 и 3 доли (96 BPM);
- legal — спокойный, достоинство без гнетущих нот: пад D-мажор,
          разреженные «пианинные» ноты, без пульса (84 BPM);
- tech  — современный лёгкий: лидийский пад C, синкопированный арп,
          аккуратный пульс (108 BPM).

Все треки: 32 c, целое число тактов (беззапаучный луп), стерео-ширина
через лёгкий детюн каналов, пик нормализован к -12 dBFS. Итоговый mp3
кладётся в assets/bgm/<cat>_loop.mp3 (CBR 160k, 44.1k).

Запуск: python3 scripts/make_bgm.py [--out-dir assets/bgm]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
PEAK_DB = -12.0


# ------------------------------------------------------------------ примитивы

def _note_hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _adsr(n: int, a_s: float, d_s: float, s_level: float, r_s: float) -> np.ndarray:
    """Огибающая ADSR на n семплов (d+r вписываются в хвост)."""
    a = max(1, int(a_s * SR))
    r = max(1, int(r_s * SR))
    d = max(1, int(d_s * SR))
    env = np.ones(n)
    env[:a] = np.linspace(0.0, 1.0, a)
    if a + d < n:
        env[a:a + d] = np.linspace(1.0, s_level, d)
        env[a + d:] = s_level
    # release: линейный спад последних r семплов
    if n > r:
        env[-r:] *= np.linspace(1.0, 0.0, r)
    return env


def _place(buf: np.ndarray, start: int, sound: np.ndarray) -> None:
    """Складывает sound в buf с клипа по краям (без предупреждений)."""
    end = min(len(buf), start + len(sound))
    if start < 0 or end <= start:
        return
    buf[start:end] += sound[:end - start]


def _pad(freqs: list, dur: float, amp: float) -> np.ndarray:
    """Тёплый пад: синус + 2 мягкие гармоники, медленная атака/релиз."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        # лёгкое «дыхание» детюном
        out += np.sin(2 * np.pi * f * t) * 1.0
        out += np.sin(2 * np.pi * f * 1.003 * t) * 0.5
        out += np.sin(2 * np.pi * f * 2.0 * t) * 0.12
        out += np.sin(2 * np.pi * f * 0.5 * t) * 0.18
    env = _adsr(n, dur * 0.35, dur * 0.1, 0.8, dur * 0.4)
    return out * env * (amp / max(1, len(freqs)))


def _pluck(freq: float, dur: float, amp: float) -> np.ndarray:
    """Короткая нота-пульс: синус с экспоненциальным затуханием."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = (np.sin(2 * np.pi * freq * t) +
           0.22 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 9))
    return out * np.exp(-t * 7.5) * amp


def _thump(dur: float, amp: float) -> np.ndarray:
    """Мягкий низкий пульс (не кик, без щелчка)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 62.0 * np.exp(-t * 3.0) + 48.0
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 6.0) * amp


def _norm_stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Пик -> -12 dBFS, стерео-интерлив в int16."""
    peak = max(np.abs(left).max(), np.abs(right).max(), 1e-9)
    k = 10 ** (PEAK_DB / 20.0) / peak
    stereo = np.empty(len(left) * 2, dtype=np.int16)
    stereo[0::2] = np.clip(left * k * 32767, -32768, 32767).astype(np.int16)
    stereo[1::2] = np.clip(right * k * 32767, -32768, 32767).astype(np.int16)
    return stereo


def _write_mp3(samples: np.ndarray, out: Path) -> None:
    tmp = out.with_suffix(".wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(samples.tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp),
         "-c:a", "libmp3lame", "-b:a", "160k", str(out)], check=True)
    tmp.unlink()


# ------------------------------------------------------------------ категории

# прогрессия I - vi - IV - V в A-мажоре (тёплая, без минорной тревоги)
_NEWS_CHORDS = [
    [57, 61, 64, 69],   # A:  A3 C#4 E4  A4
    [54, 57, 61, 66],   # F#m
    [50, 57, 62, 66],   # D
    [52, 56, 59, 64],   # E
]
_NEWS_ARP = [69, 72, 76, 81, 76, 72]     # пентатоника A, светло

_LEGAL_CHORDS = [
    [50, 54, 57, 62],   # D:  D3 F#3 A3 D4
    [48, 52, 55, 60],   # G
    [45, 52, 57, 62],   # D/F#
    [47, 50, 55, 59],   # Bm (мягкий, не трагический)
]
_LEGAL_NOTES = [74, 78, 81, 86]          # разреженные «пианинные»

_TECH_CHORDS = [
    [48, 55, 60, 64],   # C:  C3 G3 C4 E4 (лидийский колорит)
    [45, 52, 57, 64],   # Am add
    [43, 50, 55, 62],   # G
    [41, 48, 55, 60],   # F
]
_TECH_ARP = [72, 76, 79, 83, 79, 76]


def make_track(category: str, dur_s: float = 32.0) -> np.ndarray:
    """Синтезирует стерео-трек категории (int16, интерлив)."""
    n = int(dur_s * SR)
    L = np.zeros(n)
    R = np.zeros(n)

    if category == "news":
        bpm = 96.0
        chords, arp = _NEWS_CHORDS, _NEWS_ARP
    elif category == "legal":
        bpm = 84.0
        chords, arp = _LEGAL_CHORDS, _LEGAL_NOTES
    elif category == "tech":
        bpm = 108.0
        chords, arp = _TECH_CHORDS, _TECH_ARP
    else:
        raise ValueError(f"неизвестная категория BGM: {category}")

    beat = 60.0 / bpm                 # длительность доли
    bar = beat * 4                    # такт 4/4
    n_bars = max(1, round(dur_s / bar))
    real_dur = n_bars * bar           # целое число тактов -> бесшовный луп

    # пады: аккорд на такт, половина перекрытия (legato-переходы)
    for bar_i in range(n_bars):
        chord = chords[bar_i % len(chords)]
        freqs = [_note_hz(m) for m in chord]
        start = int(bar_i * bar * SR)
        pad = _pad(freqs, bar * 1.6, 0.30)
        _place(L, start, pad * 0.98)
        _place(R, start, pad * 1.02)   # микро-детюн каналов

    # арп/ноты: на восьмые (news/tech) или редкие (legal)
    if category == "legal":
        for bar_i in range(n_bars):
            chord = chords[bar_i % len(chords)]
            for k in range(2):        # две ноты на такт, на 1 и 3 долях
                start = int((bar_i * bar + k * 2 * beat) * SR)
                note = arp[(bar_i * 2 + k) % len(arp)]
                pl = _pluck(_note_hz(note), 1.2, 0.16)
                _place(L, start, pl)
                _place(R, start + int(0.012 * SR), pl * 0.96)
    else:
        step = beat / 2               # восьмые
        for bar_i in range(n_bars):
            chord = chords[bar_i % len(chords)]
            root_hz = _note_hz(chord[0])
            for s in range(8):
                t_s = bar_i * bar + s * step
                # пропускаем пару восьмых для «воздуха»
                if category == "tech" and s in (3, 6):
                    continue
                note = arp[(bar_i * 8 + s) % len(arp)]
                pl = _pluck(_note_hz(note), 0.30, 0.11)
                _place(L, int(t_s * SR), pl * (1.0 if s % 2 else 0.85))
                _place(R, int(t_s * SR) + int(0.010 * SR), pl * 0.92)
            # пульс на 1 и 3 долях
            for b in (0, 2):
                _place(L, int((bar_i * bar + b * beat) * SR), _thump(0.30, 0.30))
                _place(R, int((bar_i * bar + b * beat) * SR), _thump(0.30, 0.30))

    # мягкий срез ультраниза (гул не нужен, рендер добавит highpass=180)
    spec = np.fft.rfft(L)
    freqs = np.fft.rfftfreq(len(L), 1 / SR)
    spec[freqs < 45] *= 0.3
    L = np.fft.irfft(spec, len(L))
    spec = np.fft.rfft(R)
    spec[freqs < 45] *= 0.3
    R = np.fft.irfft(spec, len(R))

    # подгонка под целевую длительность (луп по тактам)
    L = L[:int(real_dur * SR)]
    R = R[:int(real_dur * SR)]
    return _norm_stereo(L, R)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="assets/bgm")
    ap.add_argument("--categories", default="news,legal,tech")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for cat in [c.strip() for c in args.categories.split(",") if c.strip()]:
        out = out_dir / f"{cat}_loop.mp3"
        print(f"[bgm] синтез {cat}: {out} ...")
        samples = make_track(cat)
        _write_mp3(samples, out)
        dur = len(samples) / 2 / SR
        print(f"[bgm] {cat}: {dur:.1f} c, {out.stat().st_size / 1024:.0f} КиБ")
    print("[bgm] готово")
    return 0


if __name__ == "__main__":
    sys.exit(main())
