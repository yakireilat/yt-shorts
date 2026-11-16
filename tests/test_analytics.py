"""Offline test of the learning loop with a simulated channel (no YouTube access needed).
Run: .venv/bin/python -m tests.test_analytics
"""
import json
import random
import tempfile
from pathlib import Path

from shorts import analytics, config, db


def make_run(root: Path, i: int, hook: int, drop_scene: int):
    d = root / f"run{i}"
    d.mkdir(parents=True)
    scenes = [{"start": k * 5.0, "end": (k + 1) * 5.0, "words": []} for k in range(8)]
    (d / "timeline.json").write_text(json.dumps({"duration": 40.0, "scenes": scenes}))
    (d / "qa.json").write_text(json.dumps({"review": {"hook": hook, "readability": 7, "design": 6, "match": 6,
                                                      "overall": hook * 0.6 + 2.5}}))
    spec = {"title": f"Short {i}", "pillar": ["Money", "Space"][i % 2], "theme": "midnight",
            "scenes": [{"type": t, "narration": f"line {k}", "headline": f"h{k}"} for k, t in
                       enumerate(["hook", "statement", "stat", "diagram", "compare", "map", "beforeafter", "outro"])]}
    return d, spec


def main():
    rng = random.Random(7)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg = config.load()
        cfg["paths"] = {"out": str(td / "out"), "db": str(td / "shorts.db")}
        con = db.connect(cfg)
        truth = {}
        for i in range(8):
            hook = rng.randint(4, 9)
            d, spec = make_run(td / "out", i, hook, drop_scene=3)
            db.insert_video(con, f"run{i}", spec, d / "final.mp4", 40.0, True, [], "uploaded", hook)
            con.execute("update videos set youtube_id=? where run_id=?", (f"vid{i}", f"run{i}"))
            truth[f"vid{i}"] = hook
        con.commit()

        def fake_stats(cfg, ids):  # retention grows with hook score, like a real channel would show
            return {v: {"views": 500, "likes": 20, "comments": 1, "avg_view_pct": 40 + 6 * truth[v] + rng.random(),
                        "avg_view_sec": 20, "subs_gained": 1} for v in ids}

        def fake_curve(cfg, vid):  # big loss in the first 10% and around the diagram scene (35-45%)
            h = truth[vid]
            return [(x / 100, max(0.1, 1.0 - (0.5 - h * 0.04) * min(1, x / 10) - (0.15 if x > 40 else 0) - x * 0.002))
                    for x in range(0, 101)]

        written = {}
        analytics.write_lessons = lambda cfg, feats, cal: written.setdefault("lessons", (len(feats), cal)) and "ok"
        analytics.rel = lambda p: td / Path(p).name if p.startswith("data") else config.rel(p)
        res = analytics.learn(cfg, force=True, fetch=(fake_stats, fake_curve))

        assert res, "learn returned nothing"
        cal = res["calibration"]
        assert cal["hook"] is not None and cal["hook"] > 0.8, cal          # hook score predicts retention
        f0 = res["features"][0]
        assert f0["worst_scenes"][0]["scene"] in (0, 7, 8), f0["worst_scenes"]  # biggest loss: hook window
        assert any(w["scene"] == 7 or w["scene"] == 0 or w["type"] in ("diagram", "compare", "hook")
                   for w in f0["worst_scenes"])
        assert (td / "calibration.json").exists()
        assert "hook" in analytics.calibration_note(cfg)
        print("calibration:", cal)
        print("worst scenes of first short:", f0["worst_scenes"])
        print("PASS")


if __name__ == "__main__":
    main()
