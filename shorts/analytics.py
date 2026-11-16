"""Learning from real viewers (step 9). Runs automatically from `shorts run`, no approval needed.

1. Pull each uploaded short's audience-retention curve (YouTube Analytics: audienceWatchRatio over
   elapsedVideoTimeRatio) and map it onto that short's own scene timeline -> which scene loses viewers.
2. Calibrate the Claude review: which sub-score (hook / readability / design / match) actually predicts
   real retention? The result is fed back into the reviewer prompt.
3. Once a day, Claude turns the evidence into a short list of concrete lessons (data/lessons.md) that is injected
   into every new script prompt. The machine gets better every day without anyone touching it.
"""
import json
import statistics
import subprocess
import time
from pathlib import Path

from . import db
from .config import rel

MIN_VIEWS = 100  # below this, retention numbers are noise


# ---------- per-video features ----------
def scene_drops(curve: list[tuple[float, float]], timeline: dict, duration: float) -> list[dict]:
    """Viewer loss inside each scene. curve = [(elapsed_ratio 0..1, watch_ratio)], watch_ratio ~1.0 at start."""
    out = []
    pts = sorted(curve)
    at = lambda t: _interp(pts, t / duration) if duration else 0.0
    for i, sc in enumerate(timeline["scenes"]):
        a, b = at(sc["start"]), at(min(sc["end"], duration))
        span = max(0.1, sc["end"] - sc["start"])
        out.append({"scene": i, "start": sc["start"], "end": sc["end"], "kept_start": round(a, 3), "kept_end": round(b, 3),
                    "loss": round(max(0.0, a - b), 3), "loss_per_sec": round(max(0.0, a - b) / span, 4)})
    return out


def _interp(pts, x):
    if not pts:
        return 0.0
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0)
    return pts[-1][1]


def features(row, stats: dict, curve, run_dir: Path) -> dict | None:
    spec = json.loads(row["spec"])
    qa_p, tl_p = run_dir / "qa.json", run_dir / "timeline.json"
    qa = json.loads(qa_p.read_text()) if qa_p.exists() else {}
    rv = qa.get("review") or {}
    f = {
        "title": spec.get("title"), "pillar": spec.get("pillar"), "theme": spec.get("theme"),
        "duration": row["duration"], "views": stats.get("views"), "avg_view_pct": stats.get("avg_view_pct"),
        "likes_per_1k": round(1000 * (stats.get("likes") or 0) / max(1, stats.get("views") or 1), 1),
        "subs_gained": stats.get("subs_gained"),
        "review": {k: rv.get(k) for k in ("hook", "readability", "design", "match", "overall")},
        "qa_score": row["score"],
        "hook_line": spec["scenes"][0]["narration"], "hook_headline": spec["scenes"][0].get("headline"),
        "scene_types": [s["type"] for s in spec["scenes"]],
        "photos": sum(1 for s in spec["scenes"] if s.get("image")),
    }
    if curve and tl_p.exists():
        tl = json.loads(tl_p.read_text())
        drops = scene_drops(curve, tl, row["duration"])
        f["kept_after_hook"] = drops[0]["kept_end"] if drops else None
        f["end_watch_ratio"] = round(curve[-1][1], 3)  # > 1.0 means people loop/rewatch
        worst = sorted(drops, key=lambda d: -d["loss_per_sec"])[:2]
        f["worst_scenes"] = [{"scene": d["scene"], "type": spec["scenes"][d["scene"]]["type"],
                              "narration": spec["scenes"][d["scene"]]["narration"], "loss": d["loss"]} for d in worst]
    return f


# ---------- calibration ----------
def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def spearman(xs, ys) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 6:
        return None
    rx, ry = _rank([p[0] for p in pairs]), _rank([p[1] for p in pairs])
    try:
        return round(statistics.correlation(rx, ry), 2)
    except statistics.StatisticsError:
        return None


def calibrate(feats: list[dict]) -> dict:
    y = [f["avg_view_pct"] for f in feats]
    cal = {k: spearman([f["review"].get(k) for f in feats], y) for k in ("hook", "readability", "design", "match", "overall")}
    cal["n"] = len(feats)
    return cal


def calibration_note(cfg) -> str:
    """Text appended to the reviewer prompt: what actually predicted retention on this channel."""
    p = rel("data/calibration.json")
    if not p.exists():
        return ""
    cal = json.loads(p.read_text())
    parts = [f"{k} {v:+.2f}" for k, v in cal.items() if k != "n" and isinstance(v, (int, float))]
    if not parts:
        return ""
    return (f"\nCHANNEL DATA (n={cal['n']} published shorts): rank-correlation of your past sub-scores with real "
            f"average % viewed: {', '.join(parts)}. Weigh the dimensions that actually predict retention more heavily "
            f"in 'overall', and be stricter there.\n")


# ---------- lessons ----------
LESSONS_PROMPT = """You are the growth analyst of a YouTube Shorts explainer channel. Below is real performance data
for every published short (avg % viewed, share of viewers still watching after the hook, rewatch ratio at the end,
the scenes where most viewers left and what was said there, the reviewer's scores, scene types, pillar).

{data}

Reviewer-score vs. real-retention correlation: {cal}

Previous lessons (keep the ones still supported, drop the ones the data now contradicts):
{prev}

Write at most 12 short, concrete, ACTIONABLE rules for the script writer that would raise average % viewed and
hook retention on THIS channel. Base each on the evidence (cite the pattern briefly in parentheses). Cover hooks,
pacing, scene types that hold or lose people, topics/pillars, length. No generic advice that isn't in the data.
Return only the bullet list in markdown.
"""


def write_lessons(cfg, feats: list[dict], cal: dict) -> str:
    prev_p = rel("data/lessons.md")
    prev = prev_p.read_text() if prev_p.exists() else "(none yet)"
    c = cfg.claude
    cmd = [c["binary"], "-p", LESSONS_PROMPT.format(data=json.dumps(feats, indent=1)[:60000], cal=json.dumps(cal), prev=prev),
           "--output-format", "json", "--disallowedTools", "Bash,Edit,Write,WebSearch,WebFetch,Read"]
    if c.get("model"):
        cmd += ["--model", c["model"]]
    import tempfile
    with tempfile.TemporaryDirectory() as td:  # empty cwd: no project context leaks into the analysis
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=c.get("timeout_sec", 600), cwd=td)
    text = (json.loads(r.stdout).get("result") or "").strip()
    if text:
        prev_p.parent.mkdir(parents=True, exist_ok=True)
        prev_p.write_text(f"<!-- generated {time.strftime('%Y-%m-%d %H:%M')} from {len(feats)} shorts -->\n{text}\n")
    return text


def lessons_for_prompt() -> str:
    p = rel("data/lessons.md")
    if not p.exists():
        return ""
    body = "\n".join(l for l in p.read_text().splitlines() if not l.startswith("<!--")).strip()
    return f"LESSONS FROM THIS CHANNEL'S REAL VIEWERS (follow them):\n{body}\n" if body else ""


# ---------- orchestration ----------
def learn(cfg, force: bool = False, fetch=None) -> dict | None:
    """Refresh retention curves, recalibrate the reviewer and rewrite lessons (at most once a day unless forced).
    `fetch` = (stats_fn, retention_fn) can be injected for tests."""
    from . import youtube
    stats_fn, ret_fn = fetch or (youtube.fetch_stats, youtube.fetch_retention)
    lp = rel("data/lessons.md")
    if not force and lp.exists() and time.time() - lp.stat().st_mtime < 86400:
        return None
    con = db.connect(cfg)
    rows = [r for r in con.execute("select * from videos where youtube_id is not null")]
    if not rows:
        return None
    stats = stats_fn(cfg, [r["youtube_id"] for r in rows])
    feats = []
    for r in rows:
        s = stats.get(r["youtube_id"], {})
        if (s.get("views") or 0) < MIN_VIEWS or s.get("avg_view_pct") is None:
            continue
        try:
            curve = ret_fn(cfg, r["youtube_id"])
        except Exception as e:
            print("[learn] retention unavailable:", e)
            curve = []
        f = features(r, s, curve, Path(r["path"]).parent)
        if f:
            feats.append(f)
    if len(feats) < int(cfg.get("learning", {}).get("min_videos", 5)):
        print(f"[learn] {len(feats)} shorts with enough views; need {cfg.get('learning', {}).get('min_videos', 5)}")
        return None
    cal = calibrate(feats)
    rel("data/calibration.json").write_text(json.dumps(cal, indent=1))
    rel("data/features.json").write_text(json.dumps(feats, indent=1))
    lessons = write_lessons(cfg, feats, cal)
    print(f"[learn] {len(feats)} shorts analysed; calibration {cal}; lessons updated")
    return {"features": feats, "calibration": cal, "lessons": lessons}
