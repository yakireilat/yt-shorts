"""`python -m shorts doctor`: check everything the hourly machine needs, with the fix for each problem."""
import shutil
import subprocess

from .config import ROOT, rel


def _ok(name, good, fix=""):
    print(f"  [{'OK' if good else '!!'}] {name}" + ("" if good else f"\n        fix: {fix}"))
    return good


def run(cfg) -> int:
    print("Shorts Machine doctor\n")
    bad = 0
    for tool, fix in [("ffmpeg", "sudo apt install ffmpeg  |  brew install ffmpeg"), ("node", "install Node 20+"),
                      (cfg.claude["binary"], "npm i -g @anthropic-ai/claude-code, then run `claude` once to log in")]:
        bad += not _ok(f"{tool} installed", bool(shutil.which(tool)), fix)
    try:
        r = subprocess.run([cfg.claude["binary"], "-p", "Reply OK", "--output-format", "json"], capture_output=True,
                           text=True, timeout=120)
        bad += not _ok("Claude CLI logged in (your subscription)", r.returncode == 0 and '"is_error":false' in r.stdout.replace(" ", ""),
                       "run `claude` once and log in with your Claude account")
    except Exception as e:
        bad += not _ok("Claude CLI responds", False, str(e))
    bad += not _ok("voice model present", rel(cfg.voice.model).exists(), "./setup.sh")
    bad += not _ok("renderer deps (node_modules)", (ROOT / "node_modules" / "playwright").exists(), "npm install")
    pub = cfg.publish
    cs, tok = rel(pub.client_secret), rel(pub.token)
    bad += not _ok("Google OAuth client file", cs.exists(),
                   f"save the Desktop-app OAuth JSON as {cs} (README: Connect YouTube)")
    if tok.exists():
        try:
            from . import youtube
            ch = youtube.channel(cfg)
            _ok(f"YouTube connected: '{ch['title']}' ({ch['subs']} subscribers)", True)
        except Exception as e:
            bad += not _ok("YouTube token valid", False, f"python -m shorts auth   ({str(e)[:120]})")
    else:
        bad += not _ok("YouTube authorized", False, "python -m shorts auth")
    bad += not _ok("publishing enabled in config.toml", bool(pub.get("enabled")), "set [publish] enabled = true")
    timer = subprocess.run(["systemctl", "--user", "is-active", "shorts.timer"], capture_output=True, text=True) \
        if shutil.which("systemctl") else None
    _ok("hourly timer active", bool(timer and timer.stdout.strip() == "active"),
        "bash deploy/install.sh   (or the cron line in deploy/README.md)")
    print("\nAll good." if not bad else f"\n{bad} problem(s) to fix.")
    return 1 if bad else 0
