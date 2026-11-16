"""Step 7: quality gate. Four layers, cheapest first; every short gets a 0-10 score and FAIL/WARN notes.

  1. script & format rules          (instant)
  2. layout check in the renderer   (render/engine.js layoutCheck -> layout.json)
  3. signal checks with FFmpeg      (loudness, true peak, black frames, frozen video, narration gaps)
  4. narration check                (faster-whisper vs script, done in pipeline before render -> asr.json)
  5. Claude as viewer               (looks at frame 0 + each scene and scores hook / readability / design / match)

A short with any FAIL is never published. Queued shorts are published best-score-first.
"""
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .compose import probe

BANNED_OPENERS = ("did you know", "in this video", "here's why", "hey guys", "welcome")


# ---------- 1. script / format ----------
def script_rules(cfg, spec, dur, info):
    f, w = [], []
    v = cfg.video
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        f.append("no audio stream")
    if (int(vs["width"]), int(vs["height"])) != (int(v.width), int(v.height)):
        f.append(f"bad resolution {vs['width']}x{vs['height']}")
    if not (float(v.min_sec) <= dur <= float(v.max_sec)):
        f.append(f"duration {dur:.1f}s outside [{v.min_sec},{v.max_sec}]")
    words = sum(len(s["narration"].split()) for s in spec["scenes"])
    if not 60 <= words <= 150:
        f.append(f"narration word count {words}")
    hook = spec["scenes"][0]["narration"]
    if hook.lower().startswith(BANNED_OPENERS):
        f.append("weak hook opener")
    if len(hook.split()) > 16:
        w.append("hook longer than 16 words")
    if not spec.get("title") or len(spec["title"]) > 100:
        f.append("bad title length")
    if not spec.get("sources"):
        f.append("no sources")
    kinds = {s["type"] for s in spec["scenes"]} - {"hook", "outro", "statement"}
    if len(kinds) < 2:
        w.append("visually monotonous: fewer than 2 visual scene types")
    return f, w


# ---------- 3. signal checks ----------
def _ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"], capture_output=True, text=True).stderr


def signal_checks(cfg, video: Path, voice: Path, timeline: dict):
    f, w, m = [], [], {}
    target = float(cfg.audio.get("target_lufs", -14))
    log = _ff(["-i", str(video), "-map", "0:a", "-af", "ebur128=peak=true"])
    mi = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    mp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", log)
    if mi:
        m["lufs"] = float(mi[-1])
        if abs(m["lufs"] - target) > 2.0:
            w.append(f"loudness {m['lufs']:.1f} LUFS (target {target})")
        if abs(m["lufs"] - target) > 5.0:
            f.append(f"loudness way off: {m['lufs']:.1f} LUFS")
    if mp:
        m["true_peak"] = float(mp[-1])
        if m["true_peak"] > -0.5:
            w.append(f"true peak {m['true_peak']:.1f} dBFS (clipping risk)")
    # black frames (anything > 0.4 s) and frozen picture (> 2.5 s; grain removed by blur so it can't mask a freeze)
    log = _ff(["-i", str(video), "-map", "0:v", "-vf",
               "scale=270:480,gblur=sigma=2,blackdetect=d=0.4:pix_th=0.06,freezedetect=n=-55dB:d=2.5"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    if blacks:
        f.append(f"black frames at {', '.join(f'{float(a):.1f}s' for a, _ in blacks[:3])}")
    freezes = re.findall(r"freeze_start: ([\d.]+)", log)
    if freezes:
        w.append(f"static picture for >2.5 s at {', '.join(f'{float(a):.1f}s' for a in freezes[:3])}")
    # dead air inside the narration (> 1.1 s), ignoring the tail
    log = _ff(["-i", str(voice), "-af", "silencedetect=n=-40dB:d=1.1"])
    end = timeline["scenes"][-1]["end"] - 0.8
    gaps = [float(a) for a in re.findall(r"silence_start: ([\d.]+)", log) if 0.3 < float(a) < end]
    if gaps:
        w.append(f"narration gap >1.1 s at {', '.join(f'{g:.1f}s' for g in gaps[:3])}")
    return f, w, m


# ---------- 5. Claude as viewer ----------
REVIEW_SCHEMA = {
    "type": "object",
    "required": ["hook", "readability", "design", "match", "overall", "verdict", "issues"],
    "properties": {
        "hook": {"type": "integer", "minimum": 1, "maximum": 10},
        "readability": {"type": "integer", "minimum": 1, "maximum": 10},
        "design": {"type": "integer", "minimum": 1, "maximum": 10},
        "match": {"type": "integer", "minimum": 1, "maximum": 10},
        "overall": {"type": "number", "minimum": 1, "maximum": 10},
        "verdict": {"type": "string", "enum": ["publish", "fix", "reject"]},
        "issues": {"type": "array", "items": {"type": "object", "required": ["scene", "problem", "fix"],
                                              "properties": {"scene": {"type": "integer"}, "problem": {"type": "string"},
                                                             "fix": {"type": "string"}}}},
    },
}

REVIEW_PROMPT = """You are a demanding YouTube Shorts editor reviewing a finished vertical short before it goes live.
Use the Read tool to look at the contact sheet: {sheet}
Panel "0s" is the very first frame (what viewers see when deciding to swipe). The translucent white shapes are
YouTube's own app UI (top bar, like/comment rail on the right, channel name + title at the bottom). That area is
covered on every phone, so do NOT count it as empty space; judge emptiness only in the open area above it. Each other panel is scene N at its
settled moment, in order. Captions in the frames are the live word-by-word subtitles.

Title: {title}
Narration by scene:
{narration}

Score 1-10 (be strict; 7 = good channel, 9 = top 1%):
- hook: does frame 0 + the first line stop a swipe? clear, intriguing, readable in under 1 second?
- readability: can every text be read on a phone at a glance? contrast, size, clutter, nothing cut off?
- design: does it look premium and consistent? balance, hierarchy, no awkward empty or crowded frames?
- match: do the visuals support exactly what is being said in each scene (photos, charts, maps, diagrams)?
overall = your weighted judgment (hook counts double).
verdict: "publish" if it's ready, "fix" if specific scenes need changes, "reject" if it is fundamentally weak,
misleading, or brainrot-ish.
issues: concrete problems with the scene number and a concrete fix (e.g. "headline too long, cut to 4 words").
Fixes must be doable with this renderer's vocabulary only: scene types hook, statement, stat (count-up number),
compare (bars), list, timeline, diagram (flow/cycle/hub boxes+arrows), map (countries, pins, route),
beforeafter (two stacked cards, optional photos), outro; a real photo (searched by keywords) on hook/statement/stat
or beforeafter cards; changing any text or number. No custom illustrations or animations beyond that.
Return the structured output.
"""


def _with_ui(im: Image.Image) -> Image.Image:
    """Approximate the YouTube Shorts app overlay (top bar, right action rail, bottom title/channel area)."""
    im = im.copy()
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    W, H = im.size
    d.rectangle([0, 0, W, 120], fill=(0, 0, 0, 70))
    d.rectangle([0, H - 380, W, H], fill=(0, 0, 0, 95))
    for k in range(5):  # like / dislike / comments / share / remix
        cy = 1020 + k * 150
        d.ellipse([W - 120, cy, W - 40, cy + 80], fill=(255, 255, 255, 150))
    d.ellipse([40, H - 330, 110, H - 260], fill=(255, 255, 255, 150))
    d.rounded_rectangle([130, H - 315, 420, H - 275], 8, fill=(255, 255, 255, 140))
    d.rounded_rectangle([40, H - 230, 760, H - 190], 8, fill=(255, 255, 255, 120))
    d.rounded_rectangle([40, H - 175, 560, H - 140], 8, fill=(255, 255, 255, 90))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def contact_sheet(stills: list[tuple[str, Path]], out: Path):
    cw, ch, cols = 360, 640, 5
    rows = (len(stills) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, (ch + 44) * rows), (16, 16, 16))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    for i, (label, p) in enumerate(stills):
        x, y = (i % cols) * cw, (i // cols) * (ch + 44)
        try:
            im = _with_ui(Image.open(p).convert("RGB")).resize((cw - 6, ch - 6))
            sheet.paste(im, (x + 3, y + 44 + 3))
        except OSError:
            pass
        d.text((x + 10, y + 6), label, fill=(255, 220, 0), font=font)
    sheet.save(out, quality=88)
    return out


def claude_review(cfg, spec, stills, outdir: Path) -> dict:
    sheet = contact_sheet(stills, outdir / "review_sheet.jpg")
    narration = "\n".join(f"{i}. [{s['type']}] {s['narration']}" for i, s in enumerate(spec["scenes"]))
    from .analytics import calibration_note
    c = cfg.claude
    prompt = REVIEW_PROMPT.format(sheet=sheet, title=spec.get("title", ""), narration=narration) + calibration_note(cfg)
    cmd = [c["binary"], "-p", prompt,
           "--output-format", "json", "--json-schema", json.dumps(REVIEW_SCHEMA), "--allowedTools", "Read",
           "--add-dir", str(outdir), "--disallowedTools", "Bash,Edit,Write,WebSearch,WebFetch"]
    if c.get("model"):
        cmd += ["--model", c["model"]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=c.get("timeout_sec", 600), cwd=outdir)
    out = json.loads(r.stdout)
    rev = out.get("structured_output")
    if not rev:
        raise RuntimeError(f"review returned no structured output: {str(out.get('result'))[:300]}")
    return rev


# ---------- aggregate ----------
def check(cfg, spec, timeline, outdir: Path):
    q = cfg.get("quality", {})
    final = outdir / "final.mp4"
    info = probe(final)
    dur = float(info["format"]["duration"])
    fails, warns = script_rules(cfg, spec, dur, info)
    report = {"duration": dur}

    lay_p = outdir / "layout.json"
    if lay_p.exists():
        lay = json.loads(lay_p.read_text())
        report["layout"] = lay
        hard = {"overflow", "off_frame", "overlap", "caption_overlap", "caption_position"}
        for x in lay:
            (fails if x["kind"] in hard else warns).append(f"layout s{x['scene']} {x['kind']}: {x['detail']}")

    f, w, m = signal_checks(cfg, final, outdir / "voice.wav", timeline)
    fails += f
    warns += w
    report["signal"] = m

    asr_p = outdir / "asr.json"
    if asr_p.exists():
        a = json.loads(asr_p.read_text())
        report["narration"] = a
        lim_f, lim_w = float(q.get("max_wer_fail", 0.15)), float(q.get("max_wer_warn", 0.06))
        bad = "; ".join(f"'{x['script']}' heard as '{x['heard']}'" for x in a["mismatches"][:4])
        if a["wer"] > lim_f:
            fails.append(f"narration mismatch WER {a['wer']:.0%}: {bad}")
        elif a["wer"] > lim_w:
            warns.append(f"narration WER {a['wer']:.0%}: {bad}")

    score = None
    if q.get("claude_review", True):
        stills = [("0s", outdir / "thumb.png")] + [(f"scene {i}", outdir / f"scene{i}.png") for i in range(len(spec["scenes"]))]
        try:
            rev = claude_review(cfg, spec, stills, outdir)
            report["review"] = rev
            score = float(rev["overall"])
            if rev["verdict"] == "reject" or score < float(q.get("min_review_score", 6.0)):
                fails.append(f"review: {rev['verdict']} {score:.1f}/10")
            elif rev["verdict"] == "fix":
                warns.append(f"review asks for fixes ({score:.1f}/10)")
            for it in rev.get("issues", [])[:6]:
                warns.append(f"review s{it['scene']}: {it['problem']} -> {it['fix']}")
        except Exception as e:
            warns.append(f"review unavailable: {e}")
    base = score if score is not None else 7.0
    machine_warns = [x for x in warns if not x.startswith("review")]  # review notes are already in its score
    report["score"] = round(max(0.0, base - 0.25 * len(machine_warns) - (3 if fails else 0)), 2)
    report["needs_fix"] = bool(fails) or (score is not None and report.get("review", {}).get("verdict") == "fix"
                                          and score < float(q.get("autofix_below", 7.0)))
    report["fails"], report["warns"] = fails, warns
    (outdir / "qa.json").write_text(json.dumps(report, indent=1))
    return len(fails) == 0, fails + [f"WARN {x}" for x in warns], dur, report
