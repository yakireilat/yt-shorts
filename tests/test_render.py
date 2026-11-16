"""Smoke test: render every scene type (with and without icons) and require zero layout problems.
Run before committing renderer changes:  .venv/bin/python -m tests.test_render
"""
import json
import subprocess
import tempfile
from pathlib import Path

from shorts import icons
from shorts.config import ROOT

SCENES = [
    {"type": "hook", "headline": "This tower hides a giant ball", "emphasis": ["giant"], "icon": "building"},
    {"type": "statement", "kicker": "The puzzle", "headline": "So why winter?", "icon": "snowflake"},
    {"type": "stat", "kicker": "Taipei 101", "value": 660, "suffix": " t", "label": "steel ball, floors 87 to 92", "icon": "weight"},
    {"type": "stat", "value": 17, "suffix": "%", "label": "of the intestine where cubes form"},
    {"type": "compare", "headline": "Then vs now", "items": [{"label": "1900", "value": 23.5, "display": "23.5 h"},
                                                            {"label": "Today", "value": 24, "display": "24 h"}]},
    {"type": "compare", "headline": "Where a dollar goes", "items": [{"label": "Studio", "value": 52, "display": "52¢"},
        {"label": "Rent", "value": 20, "display": "20¢"}, {"label": "Staff", "value": 15, "display": "15¢"}, {"label": "Left", "value": 3, "display": "3¢"}]},
    {"type": "list", "headline": "Only one direction flips", "items": [{"label": "Left-right: unchanged"}, {"label": "Up-down: unchanged"}, {"label": "Front-back: reversed"}]},
    {"type": "timeline", "headline": "How time got zones", "items": [{"label": "1883", "display": "Railroads pick 4 zones"}, {"label": "1884", "display": "Greenwich is zero"}, {"label": "1918", "display": "Congress makes it law"}]},
    {"type": "diagram", "layout": "flow", "headline": "How a fridge moves heat", "items": [{"label": "Compressor squeezes gas", "display": "gas gets hot"}, {"label": "Coils dump heat"}, {"label": "Valve drops pressure"}, {"label": "Cold coils absorb heat"}]},
    {"type": "diagram", "layout": "cycle", "headline": "The water cycle", "items": [{"label": "Evaporation"}, {"label": "Condensation"}, {"label": "Rain"}]},
    {"type": "diagram", "layout": "hub", "headline": "Why salt was money", "items": [{"label": "Salt"}, {"label": "Preserving food"}, {"label": "Taxes"}, {"label": "Trade routes"}, {"label": "Wages"}]},
    {"type": "map", "headline": "Four zones, one country", "regions": ["United States"], "places": [
        {"label": "New York", "lat": 40.7, "lon": -74.0}, {"label": "Chicago", "lat": 41.9, "lon": -87.6},
        {"label": "Denver", "lat": 39.7, "lon": -105.0}, {"label": "San Francisco", "lat": 37.8, "lon": -122.4}]},
    {"type": "map", "headline": "The Silk Road", "route": True, "places": [{"label": "Xi'an", "lat": 34.3, "lon": 108.9},
        {"label": "Samarkand", "lat": 39.7, "lon": 67.0}, {"label": "Constantinople", "lat": 41.0, "lon": 29.0}]},
    {"type": "beforeafter", "headline": "What a cinema really sells", "items": [{"label": "Myth", "display": "Theaters profit from movies"},
                                                                            {"label": "Reality", "display": "The lobby is the real store"}]},
    {"type": "beforeafter", "headline": "Same moment, two towns", "items": [{"label": "Town A", "display": "Noon at 12:00"}, {"label": "Town B", "display": "12:07 at the same moment"}]},
    {"type": "outro", "headline": "Angle beats distance", "icon": "sun"},
]


def main():
    spec = {"theme": "midnight", "scenes": [dict(s, narration="Before this. After that now.") for s in SCENES]}
    icons.resolve(spec)
    tl, t = [], 0.1
    for _ in SCENES:
        tl.append({"start": t, "end": t + 4.0, "words": [{"w": "Before", "s": t + 0.1, "e": t + 0.4}, {"w": "this.", "s": t + 0.4, "e": t + 0.8},
                                                        {"w": "After", "s": t + 1.6, "e": t + 1.9}, {"w": "that", "s": t + 1.9, "e": t + 2.2},
                                                        {"w": "now.", "s": t + 2.2, "e": t + 2.6}]})
        t += 4.0
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        for theme in ("midnight", "paper"):
            spec["theme"] = theme
            job = {"spec": spec, "timeline": {"duration": 0.05, "scenes": tl}, "series": "The Hidden Why",
                   "video": {"workers": 1}, "stills": [{"t": 0.0, "path": f"{td}/f0.png"}], "layoutOut": f"{td}/lay.json"}
            Path(td, "job.json").write_text(json.dumps(job))
            r = subprocess.run(["node", str(ROOT / "render" / "render.mjs"), f"{td}/job.json", f"{td}/x.mp4"],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                print(f"[{theme}] RENDER CRASH:\n{r.stderr[-1500:]}")
                failures += 1
                continue
            issues = json.loads(Path(td, "lay.json").read_text())
            for x in issues:
                print(f"[{theme}] scene {x['scene']} ({x['type']}) {x['kind']}: {x['detail']}")
            failures += len(issues)
    print("PASS" if not failures else f"FAIL ({failures})")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
