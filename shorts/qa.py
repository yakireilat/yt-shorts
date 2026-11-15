"""Step 7: automated quality gate. A short that fails is kept on disk but never published."""
from .compose import probe

BANNED_OPENERS = ("did you know", "in this video", "here's why", "hey guys", "welcome")


def check(cfg, spec, timeline, path):
    notes = []
    v = cfg.video
    info = probe(path)
    dur = float(info["format"]["duration"])
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        notes.append("no audio stream")
    if (int(vs["width"]), int(vs["height"])) != (int(v.width), int(v.height)):
        notes.append(f"bad resolution {vs['width']}x{vs['height']}")
    if not (float(v.min_sec) <= dur <= float(v.max_sec)):
        notes.append(f"duration {dur:.1f}s outside [{v.min_sec},{v.max_sec}]")
    words = sum(len(s["narration"].split()) for s in spec["scenes"])
    if not 60 <= words <= 150:
        notes.append(f"narration word count {words}")
    hook = spec["scenes"][0]["narration"].lower()
    if hook.startswith(BANNED_OPENERS):
        notes.append("weak hook opener")
    if len(spec["scenes"][0]["narration"].split()) > 16:
        notes.append("hook too long")
    if len(spec.get("title", "")) > 100 or not spec.get("title"):
        notes.append("bad title length")
    if not spec.get("sources"):
        notes.append("no sources")
    return len(notes) == 0, notes, dur
