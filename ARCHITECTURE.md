# Shorts Machine — Architecture

A fully automatic, local, open-source YouTube Shorts factory.
**Brains:** your Claude subscription via the `claude` CLI in headless mode (`claude -p`).
**Everything else:** open-source and running on your laptop / mini-PC / home server. No paid APIs.

---

## 1. Design principles

1. **Not brainrot.** Every short teaches one real, surprising, *verifiable* idea.
   Claude researches with web search, then a second pass fact-checks the script.
2. **Designed, not generated.** Instead of noisy AI video (needs a big GPU, looks generic, gets flagged as
   "mass-produced"), each short is **code-rendered motion graphics**: kinetic typography, animated stats,
   bar charts, timelines — the look of a premium explainer channel. Deterministic, crisp, brandable, CPU-only.
3. **Local-first.** One machine, one cron/systemd timer, one SQLite file.
4. **Feedback loop.** YouTube Analytics → SQLite → injected into the next ideation prompt, so the machine
   learns which topics/hooks retain viewers.

## 2. Pipeline (one run = one Short)

```
 ┌───────────┐   ┌───────────┐   ┌────────┐   ┌─────────┐   ┌──────────┐   ┌────────┐   ┌─────────┐
 │ 1 IDEATE  │──▶│ 2 FACT-   │──▶│ 3 TTS  │──▶│ 4 MUSIC │──▶│ 5 RENDER │──▶│ 6 MUX  │──▶│ 7 QA    │
 │ claude -p │   │  CHECK    │   │ Kokoro │   │ + SFX   │   │ Chromium │   │ ffmpeg │   │ checks  │
 │ +WebSearch│   │ claude -p │   │ (ONNX) │   │ numpy   │   │ frames   │   │ -14LUFS│   │         │
 └───────────┘   └───────────┘   └────────┘   └─────────┘   └──────────┘   └────────┘   └────┬────┘
       ▲                                                                                     │
       │ top/bottom performers                                                               ▼
 ┌───────────┐                                                                         ┌──────────┐
 │ 9 LEARN   │◀──────────────── YouTube Analytics API ◀────────────────────────────────│ 8 PUBLISH│
 │ SQLite    │                                                                         │ Data API │
 └───────────┘                                                                         └──────────┘
```

| Step | Module | Tool (open source / subscription) | Output |
|---|---|---|---|
| 1 Ideate | `shorts/ideate.py` | `claude -p --json-schema` + WebSearch | scene-spec JSON (scenes, narration, metadata) |
| 2 Fact-check | `shorts/ideate.py` | second `claude -p` pass | corrected spec |
| 3 Voice | `shorts/tts.py` | **Kokoro-82M** (Apache-2.0, ONNX, CPU, ~real-time×10) | per-scene WAV + word timings |
| 4 Music/SFX | `shorts/music.py` | procedural synth (numpy) or your CC0 tracks in `assets/music/` | music bed, whooshes |
| 5 Render | `render/render.mjs` + `render/template.html` | **Playwright + Chromium**, HTML/CSS/SVG, deterministic `renderAt(t)` | 1080×1920 30fps frames → H.264 |
| 6 Mux | `shorts/compose.py` | **FFmpeg** (sidechain ducking, loudnorm −14 LUFS) | `final.mp4` |
| 7 QA | `shorts/qa.py` | ffprobe | pass/fail + reasons |
| 8 Publish | `shorts/publish.py` | YouTube Data API v3 (free) | video id |
| 9 Learn | `shorts/analytics.py` | YouTube Analytics API (free) | stats in SQLite → next prompt |

Scheduler: `systemd` timer or cron calls `python -m shorts run` every hour.
State: `data/shorts.db` (topics, videos, stats). Artifacts: `out/<run-id>/`.

### Why not Higgsfield-style AI video?
Open models (Wan 2.x, LTX-Video, HunyuanVideo) are good but need 12–24 GB VRAM and minutes per clip,
and generic AI b-roll is exactly what the July-2025 YPP "inauthentic / mass-produced content" policy targets.
The renderer has a **plug-in slot** (`image` scene backgrounds) so if you later add a GPU box running
ComfyUI + FLUX/Wan, you can feed generated stills/clips in — but the core look never depends on it.

## 3. YouTube Shorts — algorithm best practice baked in

**What the Shorts feed optimises for:** *viewed vs. swiped-away* rate in the first ~1–2 s, then
**average percentage viewed** (≥ 80–100%+ with loops is great), then rewatches, likes/shares/subscribes.

Baked into the prompt + renderer:
- **Hook in the first 1.5 s**: on-screen headline appears at frame 0 (no logo intro, no fade from black),
  narration starts within 0.2 s, hook = curiosity gap or bold claim, never "In this video…".
- **Length 30–50 s**: long enough to rank as substance, short enough for >90% retention.
- **Visual change every 2–4 s**: new scene, number counter, chart animation, or caption emphasis.
- **Word-synced captions** (most viewers watch muted at first), kept inside the **safe zone**
  (avoid top ~12%, bottom ~22%, right ~14% where Shorts UI sits).
- **Seamless loop**: the last line flows back into the first line, so replays count as rewatches.
- **Payoff late**: the answer to the hook is delivered in the final third (retention).
- **One idea per short**, one consistent **series format** per channel (algorithm learns the audience).
- **Metadata**: clear searchable title (< 60 chars, no clickbait lies), 1–2 line description, 3–5 hashtags,
  `#shorts` optional. Category: Education (27).
- **Disclosure**: synthetic-voice flag set (`containsSyntheticMedia`) — no reach penalty, avoids strikes.
- **Cadence**: consistency beats volume. See §5 about "every hour".

## 4. Content strategy (default niche)

Series: **"The Hidden Why"** — 40-second explainers of surprising science, engineering, history and economics
behind everyday things ("Why airplane windows are round", "Why your phone battery lies at 1%").
Swap in `config.toml → [channel]`. Good alternatives: *Data in 45s* (stat-driven), *History's tiny details*,
*How it's made — physics*, *Money mechanics*.

## 5. Hard constraints you must know (honest list)

1. **API quota.** A new Google Cloud project gets 10,000 units/day; one upload costs ~1,600 →
   **max ~6 uploads/day**. Hourly (24/day) requires a free **quota extension request** (YouTube API audit form).
   Until then the machine renders hourly into a **queue** and publishes up to `max_uploads_per_day`.
2. **Unverified API projects upload as *private-locked*.** Until your OAuth app passes the YouTube API
   compliance audit, videos uploaded via API are forced private. Submit the audit early (free; takes days–weeks).
   Meanwhile you can upload the queue manually from `out/queue/`.
3. **24 shorts/day is not recommended for a new channel.** It dilutes per-video signals and looks like
   mass production. Recommended ramp: **2/day for weeks 1–3 → 4/day → 8/day** once avg viewed % > 70%.
   The machine still *produces* hourly so you have a buffer and choose the best ones (QA score).
4. **Claude subscription limits.** Each short ≈ 2 headless calls. 24/day fits comfortably on Pro/Max,
   but the runner backs off and retries if you hit a usage window.
5. **The device must be on.** Laptop sleeping = no shorts. A $100 mini-PC or old laptop with lid-closed
   + systemd is ideal. No GPU needed.

## 6. Roadmap (steps)

- [x] **Step 1 — Skeleton & config**: repo layout, config, SQLite.
- [x] **Step 2 — Script engine**: Claude headless + JSON schema + research + fact-check + dedupe.
- [x] **Step 3 — Voice**: Kokoro ONNX, per-scene synthesis, word timings.
- [x] **Step 4 — Motion-graphics renderer**: 7 scene types, captions, progress bar, brand palette.
- [x] **Step 5 — Audio design & mux**: procedural music bed, whooshes, ducking, loudness.
- [x] **Step 6 — QA gate**.
- [x] **Step 7 — Publisher** (OAuth, upload, queue, daily cap, scheduled publishAt).
- [x] **Step 8 — Scheduler** (systemd timer / cron).
- [x] **Step 9 — Analytics feedback loop** (basic).
- [ ] **Step 10 — Polish**: more scene types (map, diagram, code, before/after), A/B thumbnails/titles,
      faster-whisper re-alignment for exact word timings, optional ComfyUI image backgrounds.
- [ ] **Step 11 — Multi-channel / multi-language** (Kokoro speaks 8 languages).
