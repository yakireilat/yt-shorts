"""Step 3: narration with Kokoro-82M (ONNX, CPU) + approximate word-level timings for captions."""
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import rel

SR = 24000
_kokoro = None


def _engine(cfg):
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(rel(cfg.voice.model)), str(rel(cfg.voice.voices)))
    return _kokoro


def _trim(x: np.ndarray, thr=0.012, pad=0.03):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x, 0.0
    a = max(0, idx[0] - int(pad * SR))
    b = min(len(x), idx[-1] + int(pad * SR))
    return x[a:b], a / SR


def _word_weights(words):
    """Rough duration weight per word: syllable-ish length + extra for trailing punctuation pauses."""
    w = []
    for t in words:
        core = re.sub(r"[^\w]", "", t)
        vowels = len(re.findall(r"[aeiouy]+", core.lower())) or 1
        weight = 0.55 + 0.45 * vowels + 0.02 * len(core)
        if re.search(r"\d", core):
            weight += 0.5 * len(core)  # digits are spoken long
        pause = 0.0
        if t.endswith((",", ";", ":")):
            pause = 0.6
        elif t.endswith((".", "!", "?")):
            pause = 1.0
        elif t.endswith(("—", "-")):
            pause = 0.5
        w.append((weight, pause))
    return w


def _timings(words, dur):
    w = _word_weights(words)
    total = sum(a + b for a, b in w) or 1
    scale = dur / total
    t, out = 0.0, []
    for word, (a, b) in zip(words, w):
        out.append({"w": word, "s": round(t, 3), "e": round(t + a * scale, 3)})
        t += (a + b) * scale
    return out


def _split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def synth(cfg, spec: dict, outdir: Path) -> dict:
    """Synthesize each scene; returns timeline {duration, scenes:[{start,end,words}]} and writes voice.wav."""
    k = _engine(cfg)
    v = cfg.voice
    gap = float(v.get("scene_gap_sec", 0.18))
    lead = 0.12  # narration starts ~immediately (hook!)
    chunks = [np.zeros(int(lead * SR), dtype=np.float32)]
    t = lead
    scenes = []
    for i, sc in enumerate(spec["scenes"]):
        start = t
        words = []
        for sent in _split_sentences(sc["narration"]):
            audio, _ = k.create(sent, voice=v.voice, speed=float(v.speed), lang=cfg.channel.get("language", "en-us"))
            audio, _ = _trim(np.asarray(audio, dtype=np.float32))
            d = len(audio) / SR
            for wd in _timings(sent.split(), d):
                words.append({"w": wd["w"], "s": round(t + wd["s"], 3), "e": round(t + wd["e"], 3)})
            chunks.append(audio)
            t += d
            pause = np.zeros(int(0.12 * SR), dtype=np.float32)
            chunks.append(pause)
            t += 0.12
        if i < len(spec["scenes"]) - 1:
            chunks.append(np.zeros(int(gap * SR), dtype=np.float32))
            t += gap
        scenes.append({"start": round(start, 3), "end": round(t, 3), "words": words})
    tail = 0.6
    chunks.append(np.zeros(int(tail * SR), dtype=np.float32))
    t += tail
    scenes[-1]["end"] = round(t, 3)
    voice = np.concatenate(chunks)
    peak = np.max(np.abs(voice)) or 1
    voice = voice / peak * 0.89
    sf.write(outdir / "voice.wav", voice, SR)
    return {"duration": round(len(voice) / SR, 3), "scenes": scenes}
