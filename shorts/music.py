"""Step 4: music bed + transition SFX.

If assets/music contains tracks (CC0 / licensed by you), a random one is used.
Otherwise a tasteful procedural ambient/lofi-electronic bed is synthesized (royalty-free by construction).
"""
import random
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import rel

SR = 48000

MOODS = {
    # theme -> (root midi, progression as scale degrees in minor/major, bpm, major?)
    "midnight": (45, [0, 5, 3, 4], 96, False),
    "ember": (43, [0, 3, 4, 3], 88, False),
    "mint": (48, [0, 4, 5, 3], 100, True),
    "paper": (50, [0, 5, 3, 4], 92, True),
    "ultraviolet": (44, [0, 6, 5, 4], 84, False),
}
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _env(n, a, r):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _lp_fast(x, cutoff):
    # FFT brick-ish lowpass with soft rolloff (fast for long buffers)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def procedural(theme: str, dur: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    root, prog, bpm, major = MOODS.get(theme, MOODS["midnight"])
    scale = MAJOR if major else MINOR
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    beat = 60 / bpm
    bar = beat * 4
    chord_len = bar * 2
    # pads
    for ci in range(int(dur / chord_len) + 1):
        deg = prog[ci % len(prog)]
        notes = [root + 12 + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4, 6)]
        s0 = int(ci * chord_len * SR)
        s1 = min(n, int((ci + 1) * chord_len * SR + 0.8 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        seg = np.zeros((s1 - s0, 2))
        for m in notes:
            for det, pan in ((-0.07, 0.3), (0.07, 0.7)):
                f = _hz(m + det)
                w = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt + 0.3)
                seg[:, 0] += w * (1 - pan)
                seg[:, 1] += w * pan
        seg *= _env(len(tt), 1.2, 1.2)[:, None] * 0.05
        out[s0:s1] += seg
        # bass
        bf = _hz(root - 12 + scale[deg % 7])
        b = np.sin(2 * np.pi * bf * tt) * _env(len(tt), 0.05, 0.8) * 0.12
        out[s0:s1] += b[:, None]
    # soft arpeggio plucks (8th notes)
    step = beat / 2
    for k in range(int(dur / step)):
        ci = int(k * step / chord_len)
        deg = prog[ci % len(prog)]
        pat = [0, 2, 4, 7, 4, 2, 4, 6]
        idx = deg + pat[k % 8]
        m = root + 24 + scale[idx % 7] + 12 * (idx // 7)
        s0 = int(k * step * SR)
        L = int(0.45 * SR)
        s1 = min(n, s0 + L)
        tt = np.arange(s1 - s0) / SR
        f = _hz(m)
        pl = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(6 * np.pi * f * tt)) * np.exp(-tt * 9) * 0.05
        pl *= 0.6 + 0.4 * rng.random()
        pan = 0.5 + 0.35 * np.sin(k * 0.7)
        out[s0:s1, 0] += pl * (1 - pan)
        out[s0:s1, 1] += pl * pan
    # hats + kick (subtle)
    for k in range(int(dur / beat)):
        s0 = int(k * beat * SR)
        L = int(0.25 * SR)
        s1 = min(n, s0 + L)
        tt = np.arange(s1 - s0) / SR
        kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12) * 0.22
        out[s0:s1] += kick[:, None]
        h0 = int((k + 0.5) * beat * SR)
        h1 = min(n, h0 + int(0.06 * SR))
        if h0 < n:
            hh = rng.standard_normal(h1 - h0) * np.exp(-np.arange(h1 - h0) / SR * 70) * 0.025
            out[h0:h1] += hh[:, None]
    for ch in range(2):
        out[:, ch] = _lp_fast(out[:, ch], 6500)
    # fade
    out *= _env(n, 0.02, 1.0)[:, None]
    peak = np.max(np.abs(out)) or 1
    return (out / peak * 0.8).astype(np.float32)


def whoosh(rng, length=0.55):
    n = int(length * SR)
    tt = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # sweep via moving lowpass approximated by blending two filtered versions
    lo = _lp_fast(noise, 900)
    hi = _lp_fast(noise, 5000)
    mix = np.clip(tt / length, 0, 1)
    sig = lo * (1 - mix) + hi * mix
    env = np.sin(np.pi * np.clip(tt / length, 0, 1)) ** 2
    return (sig * env * 0.18).astype(np.float32)


def tick(length=0.05):
    n = int(length * SR)
    tt = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2200 * tt) * np.exp(-tt * 120) * 0.12).astype(np.float32)


def build(cfg, spec, timeline, outdir: Path, seed: int):
    dur = timeline["duration"]
    rng = np.random.default_rng(seed)
    mdir = rel(cfg.audio.get("music_dir", "assets/music"))
    tracks = [p for p in mdir.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".flac", ".ogg", ".m4a")] if mdir.exists() else []
    music_path = outdir / "music.wav"
    if tracks:
        music_path = random.Random(seed).choice(tracks)
    else:
        sf.write(music_path, procedural(spec.get("theme", "midnight"), dur + 1, seed), SR)
    # sfx track
    n = int((dur + 1) * SR)
    sfx = np.zeros((n, 2), dtype=np.float32)
    if cfg.audio.get("sfx", True):
        for i, sc in enumerate(timeline["scenes"][1:], start=1):
            w = whoosh(rng)
            s0 = max(0, int((sc["start"] - 0.28) * SR))
            s1 = min(n, s0 + len(w))
            sfx[s0:s1, 0] += w[: s1 - s0]
            sfx[s0:s1, 1] += w[: s1 - s0]
            if spec["scenes"][i]["type"] == "stat":
                for j in range(8):
                    tk = tick()
                    a = int((sc["start"] + 0.1 + j * 0.11) * SR)
                    b = min(n, a + len(tk))
                    sfx[a:b] += tk[: b - a, None] * (1 - j / 10)
    sf.write(outdir / "sfx.wav", sfx, SR)
    return music_path, outdir / "sfx.wav"
