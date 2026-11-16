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
| 3b Photos | `shorts/images.py` | Openverse (800M+ CC/PD images) + NASA library, **Claude vision picks/rejects** | licensed photos + credits |
| 4 Music/SFX | `shorts/music.py` | procedural synth (numpy) or your CC0 tracks in `assets/music/` | music bed, whooshes |
| 5 Render | `render/render.mjs` + `render/template.html` | **Playwright + Chromium**, HTML/CSS/SVG, deterministic `renderAt(t)` | 1080×1920 30fps frames → H.264 |
| 6 Mux | `shorts/compose.py` | **FFmpeg** (sidechain ducking, loudnorm −14 LUFS) | `final.mp4` |
| 7 QA | `shorts/qa.py`, `shorts/asr.py`, `layoutCheck` in `render/engine.js` | layout check, FFmpeg, faster-whisper, Claude review | score 0–10, FAIL/WARN, auto-fix |
| 8 Publish | `shorts/publish.py` | YouTube Data API v3 (free) | video id |
| 9 Learn | `shorts/analytics.py` | YouTube Analytics API (free) | stats in SQLite → next prompt |

Scheduler: `systemd` timer or cron calls `python -m shorts run` every hour.
State: `data/shorts.db` (topics, videos, stats). Artifacts: `out/<run-id>/`.

### Real photos without a GPU
Instead of generating images, the machine **finds** them in open-licensed libraries:

| Source | What | License | Key? |
|---|---|---|---|
| **Openverse** (WordPress Foundation) | 800M+ images aggregated from Wikimedia Commons, Flickr CC, Smithsonian, the Met, museums, NASA on Flickr… | filtered to CC0 / public domain / CC BY (commercial-safe) | no |
| **NASA Image Library** | space & aeronautics imagery | public domain | no |
| *(optional later)* Pexels / Unsplash APIs | stock photos, strong for everyday objects | own free licenses | free key |

Search relevance is noisy (searching "cut onion halves" returns curries), so the writer adds a literal `image_query`
to at most 3 scenes. The fetcher builds a numbered contact sheet, and **Claude looks at it** (headless `Read` tool)
and picks the best image or rejects all of them. On a reject it suggests a better query and the fetcher retries once.
Credits go into the YouTube description automatically, as CC BY requires. Photos appear full-bleed in the top
half with a slow Ken Burns zoom, fading into the theme background, so the designed look stays consistent.

### Why not Higgsfield-style AI video?
Open models (Wan 2.x, LTX-Video, HunyuanVideo) are good but need 12–24 GB VRAM and minutes per clip,
and generic AI b-roll is exactly what the July-2025 YPP "inauthentic / mass-produced content" policy targets.
The renderer has a **plug-in slot** (`image` scene backgrounds) so if you later add a GPU box running
ComfyUI + FLUX/Wan, you can feed generated stills/clips in — but the core look never depends on it.

## 2b. Quality gate

Every short gets a **0–10 score** and FAIL/WARN notes (`out/<run>/qa.json`). A FAIL is never published, and the
publisher always takes the **highest-scoring** queued short first. Layers, cheapest first:

| Layer | How | Catches | Cost |
|---|---|---|---|
| Script rules | `qa.script_rules` | length, word count, weak hook opener, missing sources, visual monotony | free |
| **Layout check** | `layoutCheck()` runs in Chromium at each scene's settled frame and measures every element | text overflowing its box, content under the Shorts UI (top bar, title area, like/comment rail), overlapping cards/labels, captions covering content, text < 28 px | free, exact |
| **Signal** | FFmpeg `ebur128`, `blackdetect`, `freezedetect` (grain blurred out), `silencedetect` | loudness off −14 LUFS, clipping, black frames, frozen picture, dead air in narration | free |
| **Narration** | faster-whisper `small.en` on CPU (~6 s) transcribes the voice; number-aware diff against the script | TTS mispronunciations, garbled numbers/acronyms, skipped words (WER + exact phrases) | free |
| **Claude as viewer** | contact sheet of frame 0 + every scene → Claude scores hook ×2, readability, design, match | weak first frame, unreadable or cluttered frames, visuals that don't match the words, numbers that contradict the voice | 1 call |

Side benefit: Whisper's word timestamps **re-time the captions** to the real audio.

**Auto-fix:** on a FAIL, or a "fix" verdict below 7, the whole report goes back to Claude, which revises the
script: shorter headlines, words the voice can say, the reviewer's fixes. The short is re-rendered once. Both
versions stay on disk, and only the better passing one stays in the publish queue.

The final check is real viewers: the analytics loop feeds best/worst avg % viewed into the next scripts.

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

## 4. Content strategy: niche decision

**Decision: keep "The Hidden Why", sharpened to *how the world really works*.** It's one recognizable format with
six rotating **pillars**:

1. Everyday engineering · 2. Money mechanics · 3. Maps & geography · 4. The body & living things ·
5. History's hidden details · 6. Space & physics

Why this niche wins for *long-run, fully automatic* production (scored against the alternatives):

| Criterion | The Hidden Why | Geography/maps only | Finance only | History only | Pure "facts" |
|---|---|---|---|---|---|
| Endless topic supply at 24/day for years | ✅ six pillars | ⚠️ saturates | ⚠️ repeats | ✅ | ✅ |
| Facts verifiable by web search (fact-check pass) | ✅ | ✅ | ⚠️ goes stale | ✅ | ⚠️ myth-prone |
| Fits our visuals (diagram/map/stat/before-after) | ✅ all of them | maps only | charts only | timeline | weak |
| Needs no faces or footage | ✅ | ✅ | ✅ | ⚠️ wants archival | ✅ |
| Advertiser-friendly, Education category | ✅ | ✅ | ✅ (highest RPM) | ⚠️ wars/tragedy | ⚠️ |
| Survives the "inauthentic/mass-produced" policy | ✅ researched + original analysis | ✅ | ⚠️ advice risk | ✅ | ❌ |
| Evergreen (views keep coming months later) | ✅ | ✅ | ⚠️ | ✅ | ⚠️ |

Single-pillar channels are easier to *start* but run dry or repeat at high cadence. The pillar mix keeps one
promise to the viewer ("the hidden reason behind things you see every day") while giving the writer unlimited
material. Money mechanics adds higher-RPM topics, and maps/geography plays to the map scene.

**Self-optimizing mix:** each short records its pillar. `choose_pillar()` keeps 30% pure exploration and samples
the other 70% weighted by each pillar's average % viewed (squared). Pillars with fewer than 3 measured shorts get
an optimistic prior so they get tested. Over weeks the channel drifts toward what your audience retains,
without you touching it.

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
- [x] **Step 10a — More scene types**: diagram (flow / cycle / hub), map (Natural Earth, fly-in zoom, highlighted
      countries, pins, animated route), before/after (wipe reveal, optional photos).
- [x] **Step 10b — Real photos without a GPU**: Openverse + NASA, Claude vision selection, auto credits.
- [x] **Step 10c — Pillar rotation with performance weighting.**
- [x] **Step 10d — Quality gate**: layout check, FFmpeg signal checks, Whisper narration check + caption re-timing,
      Claude viewer review, scoring, auto-fix, best-first publishing.
- [ ] **Step 10e — Polish**: A/B titles, Pexels as a 3rd photo source, calibrate the review score against real retention.
- [ ] **Step 11 — Multi-channel / multi-language** (Kokoro speaks 8 languages).
