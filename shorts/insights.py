"""Self-improvement without viewers: mine every QA report for recurring problems.

`report()` prints a summary (python -m shorts insights). `recent_problems_for_prompt()` gives the script writer
the reviewer's most frequent recent complaints so the next script avoids them up front.
"""
import collections
import json
import re
from pathlib import Path

from .config import rel

THEMES = {
    "hook frame weak (no concrete subject / tension at 0s)": r"frame 0|swipe|hook",
    "on-screen content not in lockstep with narration": r"never mention|narration (says|never|only)|doesn't match|contradict|gives away|spoil",
    "photo missing, dark, or on the wrong scene": r"photo|image",
    "generic or repeated icon": r"icon",
    "text too small / low contrast": r"tiny|too small|low.contrast|hard to read|unreadable",
    "frame feels empty": r"empty|sparse|blank",
    "headline wording unclear or too long": r"headline",
    "chart/stat unclear": r"\bbar\b|chart|stat\b|label",
}


def _reports(last: int | None = None):
    files = sorted(rel("out").glob("2026*/qa.json")) + sorted(rel("out").glob("20[3-9]*/qa.json"))
    files = sorted(set(files))
    if last:
        files = files[-last:]
    for f in files:
        try:
            yield f.parent.name, json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue


def _themes(issues):
    c = collections.Counter()
    for i in issues:
        t = i.get("problem", "").lower()
        for name, pat in THEMES.items():
            if re.search(pat, t):
                c[name] += 1
    return c


def report(cfg=None) -> str:
    reps = list(_reports())
    if not reps:
        return "no QA reports yet"
    lines = [f"{len(reps)} rendered shorts\n", "run               score  hook read design match  fails"]
    subs = collections.defaultdict(list)
    for name, r in reps:
        rv = r.get("review") or {}
        for k in ("hook", "readability", "design", "match", "overall"):
            if rv.get(k) is not None:
                subs[k].append(rv[k])
        lines.append(f"{name}  {r.get('score', 0):5.2f}  {rv.get('hook', '-'):>4} {rv.get('readability', '-'):>4} "
                     f"{rv.get('design', '-'):>6} {rv.get('match', '-'):>5}  {len(r.get('fails', []))}")
    lines.append("\naverages: " + ", ".join(f"{k} {sum(v) / len(v):.1f}" for k, v in subs.items()))
    issues = [i for _, r in reps for i in (r.get("review") or {}).get("issues", [])]
    lines.append(f"\nrecurring review themes ({len(issues)} issues):")
    for name, n in _themes(issues).most_common():
        lines.append(f"  {n:3d}  {name}")
    lay = collections.Counter(x["kind"] for _, r in reps for x in r.get("layout", []))
    if lay:
        lines.append("\nlayout check findings: " + ", ".join(f"{k} x{v}" for k, v in lay.most_common()))
    return "\n".join(lines)


def recent_problems_for_prompt(last: int = 8, top: int = 4) -> str:
    reps = list(_reports(last))
    issues = [i for _, r in reps for i in (r.get("review") or {}).get("issues", [])]
    if len(reps) < 3 or not issues:
        return ""
    common = [name for name, n in _themes(issues).most_common(top) if n >= 3]
    if not common:
        return ""
    return ("THE REVIEWER'S MOST FREQUENT COMPLAINTS ABOUT RECENT SHORTS (avoid them from the start):\n"
            + "\n".join(f"- {c}" for c in common) + "\n")
