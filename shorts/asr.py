"""Narration check with faster-whisper (open source, CPU).

1. Transcribes the synthesized voice and compares it to the script -> catches TTS mispronunciations, garbled
   numbers/acronyms, skipped words (word error rate + the exact mismatched phrases).
2. Re-times caption words from the real audio (much tighter sync than the length-based estimate in tts.py).
"""
import difflib
import re
import subprocess

import numpy as np

from .config import rel

_model = None


def _load(cfg):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        q = cfg.get("quality", {})
        _model = WhisperModel(q.get("whisper_model", "small.en"), device="cpu", compute_type="int8",
                              download_root=str(rel("models/whisper")))
    return _model


def _pcm16k(path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _num_words(tok: str) -> list[str]:
    from num2words import num2words
    t = tok.replace(",", "")
    try:
        if re.fullmatch(r"\d{4}", t) and 1100 <= int(t) <= 2099:
            s = num2words(int(t), to="year")
        elif re.fullmatch(r"\d+(\.\d+)?", t):
            s = num2words(float(t) if "." in t else int(t))
        else:
            return [tok]
    except Exception:
        return [tok]
    return [w for w in re.split(r"[\s\-,]+", s.lower()) if w and w != "and"]


def normalize(word: str) -> list[str]:
    """One spoken word -> comparable tokens ('fifty-two' -> ['fifty','two'], '52%' -> ['fifty','two','percent'])."""
    w = word.lower().replace("’", "'")
    w = w.replace("%", " percent").replace("$", " dollars ").replace("&", " and ")
    out = []
    for part in re.split(r"[\s\-–—/]+", w):
        part = re.sub(r"[^\w.']", "", part).strip(".'")
        if not part:
            continue
        out += _num_words(part) if re.search(r"\d", part) else [part]
    return [t for t in out if t != "and"]


def check_and_align(cfg, voice_path, timeline: dict, spec: dict) -> dict:
    model = _load(cfg)
    segs, _ = model.transcribe(_pcm16k(voice_path), word_timestamps=True, beam_size=5, language="en", vad_filter=False)
    heard = [w for s in segs for w in s.words]

    # flatten script words (with scene index) and heard words into comparable token streams
    sw = [(si, k, w) for si, sc in enumerate(timeline["scenes"]) for k, w in enumerate(sc["words"])]
    s_tok, s_map = [], []
    for idx, (_, _, w) in enumerate(sw):
        for t in normalize(w["w"]):
            s_tok.append(t)
            s_map.append(idx)
    h_tok, h_map = [], []
    for idx, w in enumerate(heard):
        for t in normalize(w.word):
            h_tok.append(t)
            h_map.append(idx)

    sm = difflib.SequenceMatcher(a=s_tok, b=h_tok, autojunk=False)
    errors, mismatches = 0, []
    new_times: dict[int, tuple[float, float]] = {}
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(a0, a1), range(b0, b1)):
                si, hj = s_map[i], h_map[j]
                s0, e0 = new_times.get(si, (heard[hj].start, heard[hj].end))
                new_times[si] = (min(s0, heard[hj].start), max(e0, heard[hj].end))
        else:
            errors += max(a1 - a0, b1 - b0)
            said = " ".join(s_tok[a0:a1])
            got = " ".join(h_tok[b0:b1])
            mismatches.append({"script": said, "heard": got})
    wer = errors / max(1, len(s_tok))

    # re-time caption words: matched words take whisper times, unmatched are interpolated between neighbors
    flat = [w for (_, _, w) in sw]
    known = sorted(new_times)
    for idx, w in enumerate(flat):
        if idx in new_times:
            w["s"], w["e"] = round(float(new_times[idx][0]), 3), round(float(new_times[idx][1]), 3)
        else:
            prev = max((k for k in known if k < idx), default=None)
            nxt = min((k for k in known if k > idx), default=None)
            if prev is not None and nxt is not None:
                a, b = new_times[prev][1], new_times[nxt][0]
                span = (nxt - prev)
                w["s"] = round(float(a + (b - a) * (idx - prev - 1) / span), 3)
                w["e"] = round(float(a + (b - a) * (idx - prev) / span), 3)
    # several script words matched to one heard word ("twenty nineteen" -> "2019"): split its interval evenly
    i = 0
    while i < len(flat):
        j = i
        while j + 1 < len(flat) and (flat[j + 1]["s"], flat[j + 1]["e"]) == (flat[i]["s"], flat[i]["e"]):
            j += 1
        if j > i:
            a, b, n = flat[i]["s"], flat[i]["e"], j - i + 1
            for k in range(n):
                flat[i + k]["s"], flat[i + k]["e"] = round(a + (b - a) * k / n, 3), round(a + (b - a) * (k + 1) / n, 3)
        i = j + 1
    for sc in timeline["scenes"]:  # keep every word inside its scene
        for w in sc["words"]:
            w["s"] = min(max(w["s"], sc["start"]), sc["end"])
            w["e"] = min(max(w["e"], w["s"] + 0.05), sc["end"])

    # meaningful mismatches only (ignore tiny filler differences)
    real = [m for m in mismatches if len((m["script"] + m["heard"]).split()) > 1 or len(m["script"]) > 3]
    return {"wer": round(wer, 3), "mismatches": real[:12], "heard": " ".join(w.word.strip() for w in heard)}
