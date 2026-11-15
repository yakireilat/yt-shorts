"""CLI:  python -m shorts <command>

  run              produce one short, then publish the next queued one (what the hourly timer calls)
  produce          produce one short only (seed optional: --seed "space")
  build SPEC.json  render a short from an existing spec (no Claude call)
  publish          upload the oldest queued short (respects daily cap)
  stats            refresh YouTube stats (feeds the next ideation prompt)
  auth             one-time YouTube OAuth in your browser
  loop             run forever: `run` every --every seconds (alternative to cron/systemd)
"""
import argparse
import fcntl
import json
import sys
import time
import traceback

from . import pipeline
from .config import ROOT, load


def _locked(fn):
    lock = open(ROOT / "data" / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another run is in progress; exiting")
        return 0
    return fn()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shorts", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "produce", "build", "publish", "stats", "auth", "loop"])
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--config")
    ap.add_argument("--seed")
    ap.add_argument("--every", type=int, default=3600)
    a = ap.parse_args(argv)
    (ROOT / "data").mkdir(exist_ok=True)
    cfg = load(a.config)

    if a.cmd == "auth":
        from . import youtube
        return youtube.auth(cfg)
    if a.cmd == "build":
        return _locked(lambda: pipeline.build_from_spec(cfg, json.load(open(a.spec))) and 0)
    if a.cmd == "produce":
        return _locked(lambda: pipeline.produce(cfg, a.seed) and 0)
    if a.cmd == "publish":
        return _locked(lambda: pipeline.publish_next(cfg) and 0)
    if a.cmd == "stats":
        return pipeline.refresh_stats(cfg)

    def run_once():
        try:
            pipeline.produce(cfg, a.seed)
        except Exception:
            traceback.print_exc()
        try:
            pipeline.publish_next(cfg)
        except Exception:
            traceback.print_exc()
        try:
            if cfg.publish.get("enabled"):
                pipeline.refresh_stats(cfg)
        except Exception:
            traceback.print_exc()
        return 0

    if a.cmd == "run":
        return _locked(run_once)
    if a.cmd == "loop":
        while True:
            t = time.time()
            _locked(run_once)
            time.sleep(max(60, a.every - (time.time() - t)))


if __name__ == "__main__":
    sys.exit(main())
