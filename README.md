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

Every run folder contains `final.mp4`, `thumb.png`, a still per scene, `spec.json` (script + sources), audio stems
and `qa.json`: the quality report with the score, layout/loudness/narration findings and Claude's review.

## Commands

| command | what it does |
|---|---|
| `python -m shorts produce [--seed "space"]` | research + make one short (no upload) |
| `python -m shorts build out/<id>/spec.json` | re-render an existing/hand-edited script, no Claude call |
| `python -m shorts qa out/<run-id>` | re-run the quality gate on a rendered short (prints score + every issue) |
| `python -m shorts publish` | upload the highest-scoring queued short that passed QA (respects the daily cap) |
| `python -m shorts run` | produce + publish + refresh stats: **what the hourly timer calls** |
| `python -m shorts stats` | pull views / avg-% viewed; best & worst feed the next prompt |
| `python -m shorts learn` | analyse retention curves now: recalibrate the reviewer, rewrite `data/lessons.md` |
| `python -m shorts insights` | recurring QA/review problems and score averages across all rendered shorts |
| `python -m shorts auth` | one-time YouTube OAuth |
| `python -m shorts loop --every 3600` | run forever without cron/systemd |

## Connect YouTube (one-time, free, ~10 minutes)

Use **the Google account (Gmail) that owns or manages the YouTube channel**. The Cloud project could live under
another account, but using the same one avoids permission mix-ups.

**A. Google Cloud project** (<https://console.cloud.google.com>, signed in with that Gmail)
1. Create a project, e.g. `shorts-machine`.
2. *APIs & Services → Library*: enable **YouTube Data API v3** and **YouTube Analytics API**.
3. *Google Auth Platform* (formerly "OAuth consent screen"): app name e.g. "Shorts Machine", user type **External**,
   your Gmail as support and developer contact.
   - *Audience*: add your Gmail as a **test user**.
   - Then click **Publish app** (status **In production**). An unverified app is fine for your own channel; you'll
     click "Advanced → continue" once at sign-in. **Don't skip this:** in *Testing* status Google expires the
     authorization after 7 days and uploads stop silently.
4. *Clients → Create client → Desktop app*. Download the JSON and save it as `secrets/client_secret.json`.

**B. Authorize, on the machine that will run hourly**
```bash
.venv/bin/python -m shorts auth      # browser opens: pick the Gmail, then the CHANNEL (brand account) to post to
.venv/bin/python -m shorts doctor    # shows the connected channel name + anything still missing
```
Set `[publish] enabled = true` in `config.toml`, then `bash deploy/install.sh` (hourly timer). Done.

**C. YouTube API audit (so uploads aren't forced private)**

Until the audit passes, YouTube locks every API upload from a new project to **private**. The machine still works;
you'd flip videos to public in YouTube Studio by hand. Apply once, free, at the
[YouTube API Services – Audit and Quota Extension Form](https://support.google.com/youtube/contact/yt_api_form):
- **Organization / use case:** "Individual creator. Internal tool that uploads original, researched educational
  Shorts to my own channel and reads my own channel's analytics. No other users, no data shared or sold."
- **Project number:** from the Cloud console dashboard. **API client:** the Desktop OAuth client above.
- **Quota requested:** e.g. 24 uploads/day plus analytics reads (check your current quota under *APIs & Services →
  YouTube Data API v3 → Quotas*).
- They may ask for a **privacy policy URL** and screenshots or a short video of the tool. A simple page stating it
  only accesses your own channel is enough. Reviews take days to weeks; reply quickly to their emails.

## Customize

- **Niche / series / tone:** `[channel]` in `config.toml`. The prompt is in `shorts/ideate.py`.
- **Voice:** `[voice] voice` (`af_heart`, `am_michael`, `bm_george`, `am_fenrir`, ...) and `speed`.
- **Look:** `render/template.html` (CSS themes: midnight, ember, mint, paper, ultraviolet) and `render/engine.js` (animations).
- **Music:** drop tracks you have rights to (CC0, or YouTube Audio Library downloads) into `assets/music/`.
  If the folder is empty, a procedural bed is generated that's royalty-free by construction.
- **Scene types:** hook, statement, stat (count-up), compare (bar race), list, timeline, **diagram** (flow / cycle / hub),
  **map** (fly-in, highlighted countries, pins, route), **beforeafter** (stacked reveal), outro.
  Text-only scenes become posters with a big self-drawing Lucide pictogram (`shorts/icons.py`).
- **Photos:** `[images]` in config. Open-licensed photos come from Openverse, Wikimedia Commons and NASA, and Claude visually approves each one.
  Searches are cached for 7 days and back off on rate limits. For hourly production, register a free Openverse
  API app (`curl -X POST https://api.openverse.org/v1/auth_tokens/register/ -d name=... -d description=... -d email=...`)
  and export `OPENVERSE_CLIENT_ID` / `OPENVERSE_CLIENT_SECRET` (e.g. in the systemd unit) for much higher limits.
  Credits are added to the description. Set `enabled = false` for pure motion graphics.
- **Pillars:** `[channel] pillars`. The machine rotates through them and favors the ones your viewers watch longest.

## Requirements

Python 3.11+, Node 20+, FFmpeg, the `claude` CLI logged in with your subscription. No GPU needed:
a 48 s short renders in about 3–6 min on a 4-core laptop.
