"""Orchestrates one full run: idea -> script -> voice -> music -> render -> mux -> QA -> (publish)."""
import json
import random
import subprocess
import time
from pathlib import Path

from . import db, ideate, music, qa, tts
from .compose import mux
from .config import ROOT, rel


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def build_from_spec(cfg, spec: dict, run_id: str | None = None) -> tuple[Path, dict, list, float, bool]:
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    outdir = rel(cfg.paths.out) / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    spec = ideate.normalize(spec, cfg)
    (outdir / "spec.json").write_text(json.dumps(spec, indent=1))

    log("voice: synthesizing narration")
    timeline = tts.synth(cfg, spec, outdir)
    (outdir / "timeline.json").write_text(json.dumps(timeline, indent=1))
    log(f"voice: {timeline['duration']:.1f}s")

    seed = random.randrange(1 << 30)
    log("audio: music bed + sfx")
    music_path, sfx_path = music.build(cfg, spec, timeline, outdir, seed)

    log("render: motion graphics")
    v = cfg.video
    job = {
        "spec": spec, "timeline": timeline, "series": cfg.channel.series_name,
        "handle": cfg.channel.get("handle_cta", ""), "captions": True,
        "video": {"width": v.width, "height": v.height, "fps": v.fps, "crf": v.crf, "workers": v.workers},
        "stills": [{"t": 0.0, "path": str(outdir / "thumb.png")},
                   *[{"t": round((s["start"] + s["end"]) / 2, 2), "path": str(outdir / f"scene{i}.png")}
                     for i, s in enumerate(timeline["scenes"])]],
    }
    (outdir / "job.json").write_text(json.dumps(job))
    subprocess.run(["node", str(ROOT / "render" / "render.mjs"), str(outdir / "job.json"), str(outdir / "video.mp4")],
                   check=True, cwd=ROOT)

    log("mux: mix + loudness")
    final = outdir / "final.mp4"
    mux(cfg, outdir / "video.mp4", outdir / "voice.wav", Path(music_path), sfx_path, timeline["duration"], final)

    ok, notes, dur = qa.check(cfg, spec, timeline, final)
    log(f"qa: {'PASS' if ok else 'FAIL'} {dur:.1f}s {notes}")
    con = db.connect(cfg)
    db.insert_video(con, run_id, spec, final, dur, ok, notes, "queued" if ok else "failed")
    return final, spec, notes, dur, ok


def produce(cfg, seed: str | None = None):
    con = db.connect(cfg)
    avoid = db.recent_topics(con)
    perf = db.performance_summary(con)
    log("ideate: researching + writing with Claude")
    spec = ideate.make_spec(cfg, avoid, perf, seed or ideate.random_seed())
    log(f"ideate: \"{spec['title']}\" ({spec['topic']})")
    return build_from_spec(cfg, spec)


def publish_next(cfg):
    from . import youtube
    if not cfg.publish.get("enabled"):
        log("publish: disabled in config (videos stay queued in out/)")
        return None
    con = db.connect(cfg)
    if db.uploads_last_24h(con) >= int(cfg.publish.get("max_uploads_per_day", 6)):
        log("publish: daily cap reached; leaving in queue")
        return None
    row = con.execute("select * from videos where status='queued' and qa_ok=1 order by created_at asc limit 1").fetchone()
    if not row:
        log("publish: queue empty")
        return None
    spec = json.loads(row["spec"])
    log(f"publish: uploading \"{spec['title']}\"")
    vid = youtube.upload(cfg, spec, Path(row["path"]))
    con.execute("update videos set status='uploaded', youtube_id=?, uploaded_at=? where run_id=?",
                (vid, time.time(), row["run_id"]))
    con.commit()
    log(f"publish: https://youtube.com/shorts/{vid}")
    return vid


def refresh_stats(cfg):
    from . import youtube
    con = db.connect(cfg)
    ids = [r[0] for r in con.execute("select youtube_id from videos where youtube_id is not null")]
    if not ids:
        return
    now = time.time()
    for vid, s in youtube.fetch_stats(cfg, ids).items():
        con.execute("insert or replace into stats values(?,?,?,?,?,?,?,?)",
                    (vid, now, s["views"], s["likes"], s["comments"], s["avg_view_pct"], s["avg_view_sec"], s["subs_gained"]))
    con.commit()
    log(f"stats: refreshed {len(ids)} videos")
