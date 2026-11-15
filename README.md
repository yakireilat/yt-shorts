# Shorts Machine

A fully automatic YouTube Shorts factory: **researched, fact-checked, motion-designed explainers**, not brainrot.
It runs on your own laptop or a small always-on box, uses your **Claude subscription** (via the `claude` CLI) for
writing, and **open-source** tools for everything else: Kokoro TTS, headless Chromium, FFmpeg.

Read **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design, YouTube algorithm best practices and limits you should know about.

```
claude -p (research + script + fact-check) → open-licensed photos (Claude-vetted) → Kokoro voice → procedural music/SFX
→ HTML/CSS motion graphics rendered frame-by-frame in Chromium → FFmpeg mix (-14 LUFS) → QA → YouTube API
```

## Quick start

```bash
git clone <this repo> ~/yt-shorts && cd ~/yt-shorts
./setup.sh                                   # python venv, node + chromium, Kokoro model (~350 MB)
claude                                       # once: log in with your Claude subscription, then /exit
.venv/bin/python -m shorts produce           # → out/<run-id>/final.mp4
```

Every run folder contains `final.mp4`, `thumb.png`, a still per scene, `spec.json` (script + sources) and audio stems.

## Commands

| command | what it does |
|---|---|
| `python -m shorts produce [--seed "space"]` | research + make one short (no upload) |
| `python -m shorts build out/<id>/spec.json` | re-render an existing/hand-edited script, no Claude call |
| `python -m shorts publish` | upload the oldest queued short that passed QA (respects the daily cap) |
| `python -m shorts run` | produce + publish + refresh stats: **what the hourly timer calls** |
| `python -m shorts stats` | pull views / avg-% viewed; best & worst feed the next prompt |
| `python -m shorts auth` | one-time YouTube OAuth |
| `python -m shorts loop --every 3600` | run forever without cron/systemd |

## Connect YouTube (one-time, free)

1. In <https://console.cloud.google.com>, create a project and enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Under **OAuth consent screen**, choose External and add yourself as a test user.
   Under **Credentials**, create an *OAuth client ID* of type **Desktop app**, download the JSON and save it as `secrets/client_secret.json`.
3. Run `.venv/bin/python -m shorts auth`. A browser opens; pick the channel.
4. In `config.toml`, set `publish.enabled = true`.
5. **Important:** until your API project passes Google's free *YouTube API Services audit*, API uploads are **locked to private**.
   Apply for the audit and quota extension early using the "YouTube API Services – Audit and Quota Extension Form".
   Default quota is about 6 uploads a day.
6. Schedule it: [deploy/README.md](deploy/README.md).

## Customize

- **Niche / series / tone:** `[channel]` in `config.toml`. The prompt is in `shorts/ideate.py`.
- **Voice:** `[voice] voice` (`af_heart`, `am_michael`, `bm_george`, `am_fenrir`, ...) and `speed`.
- **Look:** `render/template.html` (CSS themes: midnight, ember, mint, paper, ultraviolet) and `render/engine.js` (animations).
- **Music:** drop tracks you have rights to (CC0, or YouTube Audio Library downloads) into `assets/music/`.
  If the folder is empty, a procedural bed is generated that's royalty-free by construction.
- **Scene types:** hook, statement, stat (count-up), compare (bar race), list, timeline, **diagram** (flow / cycle / hub),
  **map** (fly-in, highlighted countries, pins, route), **beforeafter** (wipe reveal), outro (loop-back).
- **Photos:** `[images]` in config. Open-licensed photos come from Openverse and NASA, and Claude visually approves each one.
  Credits are added to the description. Set `enabled = false` for pure motion graphics.
- **Pillars:** `[channel] pillars`. The machine rotates through them and favors the ones your viewers watch longest.

## Requirements

Python 3.11+, Node 20+, FFmpeg, the `claude` CLI logged in with your subscription. No GPU needed:
a 48 s short renders in about 3–6 min on a 4-core laptop.
