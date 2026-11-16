"""Orchestrates one full run: idea -> script -> voice -> music -> render -> mux -> QA -> (publish)."""
import json
import random
import subprocess
import time
from pathlib import Path

from . import asr, db, icons, ideate, images, music, qa, tts
from .compose import mux
from .config import ROOT, rel


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def build_from_spec(cfg, spec: dict, run_id: str | None = None, fetch_images: bool = True):
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    outdir = rel(cfg.paths.out) / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    spec = ideate.normalize(spec, cfg)
    if fetch_images and cfg.get("images", {}).get("enabled", True):
        log("images: searching open-licensed photos")
        try:
            images.resolve(cfg, spec, outdir)
        except Exception as e:  # photos are a bonus; never fail the run over them
            log(f"images: skipped ({e})")
    try:
        icons.resolve(spec)
    except Exception as e:
        log(f"icons: skipped ({e})")
    (outdir / "spec.json").write_text(json.dumps(spec, indent=1))

    log("voice: synthesizing narration")
    timeline = tts.synth(cfg, spec, outdir)
    log(f"voice: {timeline['duration']:.1f}s")
    if cfg.get("quality", {}).get("narration_check", True):
        try:
            a = asr.check_and_align(cfg, outdir / "voice.wav", timeline, spec)
            (outdir / "asr.json").write_text(json.dumps(a, indent=1))
            log(f"narration: WER {a['wer']:.1%}, captions re-timed from audio")
        except Exception as e:
            log(f"narration: check skipped ({e})")
    (outdir / "timeline.json").write_text(json.dumps(timeline, indent=1))

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
                   *[{"t": round(max(s["start"] + 0.6, s["end"] - 0.35), 2), "path": str(outdir / f"scene{i}.png")}
                     for i, s in enumerate(timeline["scenes"])]],
        "layoutOut": str(outdir / "layout.json"),
    }
    (outdir / "job.json").write_text(json.dumps(job))
    subprocess.run(["node", str(ROOT / "render" / "render.mjs"), str(outdir / "job.json"), str(outdir / "video.mp4")],
                   check=True, cwd=ROOT)

    log("mux: mix + loudness")
    final = outdir / "final.mp4"
    mux(cfg, outdir / "video.mp4", outdir / "voice.wav", Path(music_path), sfx_path, timeline["duration"], final)

    log("qa: layout + signal + narration + Claude review")
    ok, notes, dur, report = qa.check(cfg, spec, timeline, outdir)
    log(f"qa: {'PASS' if ok else 'FAIL'} score {report['score']}/10, {dur:.1f}s")
    for n in notes:
        log(f"    - {n}")
    con = db.connect(cfg)
    db.insert_video(con, run_id, spec, final, dur, ok, notes, "queued" if ok else "failed", report["score"])
    return final, spec, notes, dur, ok, report


def produce(cfg, seed: str | None = None):
    con = db.connect(cfg)
    avoid = db.recent_topics(con)
    perf = db.performance_summary(con)
    log("ideate: researching + writing with Claude")
    pillar = ideate.choose_pillar(cfg, db.pillar_stats(con))
    log(f"ideate: pillar = {pillar}")
    spec = ideate.make_spec(cfg, avoid, perf, seed or "", pillar)
    log(f"ideate: \"{spec['title']}\" ({spec['topic']})")
    result = build_from_spec(cfg, spec)
    retries = int(cfg.get("quality", {}).get("auto_fix_retries", 1))
    for _ in range(retries):
        final, spec_used, notes, _, ok, report = result
        if not report.get("needs_fix"):
            break
        log("autofix: asking Claude to revise the script for the QA problems, then re-rendering")
        try:
            fixed = ideate.revise(cfg, spec_used, report)
        except Exception as e:
            log(f"autofix: revision failed ({e})")
            break
        time.sleep(1)  # distinct run id
        new = build_from_spec(cfg, fixed, fetch_images=False)
        # keep both on disk; only the better passing version stays in the publish queue
        con = db.connect(cfg)
        worse, better = sorted([result, new], key=lambda r: (r[4], r[5]["score"]))
        con.execute("update videos set status='superseded' where path=? and status='queued'", (str(worse[0]),))
        con.commit()
        log(f"autofix: kept score {better[5]['score']} over {worse[5]['score']}")
        result = better
    return result


def publish_next(cfg):
    from . import youtube
    if not cfg.publish.get("enabled"):
        log("publish: disabled in config (videos stay queued in out/)")
        return None
    con = db.connect(cfg)
    if db.uploads_last_24h(con) >= int(cfg.publish.get("max_uploads_per_day", 6)):
        log("publish: daily cap reached; leaving in queue")
        return None
    # best first: highest QA score among fresh shorts, newest wins ties
    row = con.execute("select * from videos where status='queued' and qa_ok=1 and created_at > ? "
                      "order by coalesce(score, 0) desc, created_at desc limit 1", (time.time() - 7 * 86400,)).fetchone()
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
