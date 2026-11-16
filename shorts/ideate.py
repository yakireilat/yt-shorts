"""Step 1+2: topic research, script + scene spec, fact-check — via the Claude CLI (your subscription)."""
import json
import random
import subprocess
import tempfile
import time

THEMES = ["midnight", "ember", "mint", "paper", "ultraviolet"]

SCENE_TYPES = ["hook", "statement", "stat", "compare", "list", "timeline", "diagram", "map", "beforeafter", "outro"]

SPEC_SCHEMA = {
    "type": "object",
    "required": ["topic", "pillar", "title", "description", "hashtags", "tags", "theme", "sources", "scenes"],
    "properties": {
        "pillar": {"type": "string", "description": "which content pillar this short belongs to (exact name given)"},
        "topic": {"type": "string", "description": "short canonical topic name for dedupe"},
        "title": {"type": "string", "description": "YouTube title, <= 60 chars, curiosity + clarity, no lies"},
        "description": {"type": "string", "description": "1-2 sentences + the key source in plain text"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 15},
        "theme": {"type": "string", "enum": THEMES},
        "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs or citations"},
        "scenes": {
            "type": "array",
            "minItems": 5,
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["type", "narration"],
                "properties": {
                    "type": {"type": "string", "enum": SCENE_TYPES},
                    "narration": {"type": "string", "description": "exact words spoken in this scene"},
                    "kicker": {"type": "string", "description": "tiny uppercase label above the headline, 1-3 words"},
                    "headline": {"type": "string", "description": "big on-screen text, max ~7 words"},
                    "emphasis": {"type": "array", "items": {"type": "string"},
                                 "description": "1-2 words of the headline to highlight"},
                    "value": {"type": "number", "description": "stat scene: the number to count up to"},
                    "decimals": {"type": "integer"},
                    "prefix": {"type": "string"},
                    "suffix": {"type": "string", "description": "e.g. '%', 'x', ' km', 'M'"},
                    "label": {"type": "string", "description": "stat scene: what the number means, short"},
                    "items": {
                        "type": "array", "maxItems": 5,
                        "items": {
                            "type": "object",
                            "required": ["label"],
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "number"},
                                "display": {"type": "string"},
                                "image_query": {"type": "string", "description": "beforeafter only: photo search"},
                            },
                        },
                    },
                    "layout": {"type": "string", "enum": ["flow", "cycle", "hub"], "description": "diagram layout"},
                    "places": {
                        "type": "array", "maxItems": 4,
                        "items": {"type": "object", "required": ["label", "lat", "lon"],
                                  "properties": {"label": {"type": "string"}, "lat": {"type": "number"},
                                                 "lon": {"type": "number"}}},
                    },
                    "regions": {"type": "array", "items": {"type": "string"}, "maxItems": 8,
                                "description": "map: English country names to highlight"},
                    "route": {"type": "boolean", "description": "map: draw an animated path through places in order"},
                    "image_query": {"type": "string", "description": "optional literal photo search, 2-4 words"},
                    "icon": {"type": "string", "description": "hook/statement/outro/stat: 1-3 comma-separated concrete keywords for a line pictogram"},
                    "image_source": {"type": "string", "enum": ["openverse", "nasa"]},
                },
            },
        },
    },
}

GUIDE = """
You are the head writer of a premium YouTube Shorts explainer series. You write for retention AND truth.

SERIES: "{series}"
NICHE: {niche}
AUDIENCE: {audience}
TONE: {tone}

ABSOLUTE RULES
- One idea per short. It must be genuinely surprising, true and verifiable. No myths, no "brainrot",
  no rage bait, no fake urgency, no medical/financial advice, no politics, no tragedy for clicks.
- Total narration 85-125 words (~32-48 s spoken). Plain spoken English, short sentences, no lists of numbers.
- Scene 1 is type "hook": a bold claim or curiosity gap in <= 12 spoken words. Never start with
  "Did you know", "In this video", "Here's why", or the series name. Headline shows on frame 0.
- Change something on screen every 2-4 seconds: each scene's narration should be 1-2 short sentences (6-25 words).
- Deliver the payoff (the real "why") in the last third. Build tension before it.
- Use at least one "stat" scene with a real number, and one of "compare", "list" or "timeline" when it fits.
- Last scene is type "outro": one COMPLETE sentence (no trailing "..." or dangling "because") that lands the
  takeaway and whose ending leads naturally back into the hook when the video loops. No "like and subscribe".
- Headlines: max ~7 words, punchy, not a copy of the narration. "emphasis" = 1-2 words from that headline.
- HOOK HEADLINE (frame 0, decides the swipe): <= 5 words, names the concrete subject AND the tension/mystery
  ("This tower hides a giant ball", not "A skyscraper with a pendulum"). Same claim as the spoken hook.
  Give the hook an "image_query" for the real subject whenever it is photographable.
- LOCKSTEP: everything on screen in a scene (headline, numbers, bars, list items, timeline events, labels) must
  be said or directly implied by THAT scene's narration. No extra bars or facts the voice never mentions, and no
  timeline/list item that gives away a later scene's reveal.
- compare: 2-4 items with numeric "value" (same unit) and "display" (formatted, e.g. "1,200 km/h").
- list: 2-4 items with short "label" (<= 5 words).
- timeline: 2-5 items, "label" = year/date, "display" = what happened (<= 6 words).
- stat: "value" numeric, plus prefix/suffix/decimals and a short "label".
- diagram: explains a MECHANISM. "layout": flow (cause -> effect chain, 2-5 steps, top to bottom), cycle (3-5 steps
  that loop), hub (items[0] is the center, 2-4 satellites). items: "label" <= 4 words; "display" only if essential, <= 4 words.
- map: when WHERE matters. "places": 1-4 with accurate decimal "lat"/"lon" and short "label"; optional "regions"
  (country names to highlight); "route": true to draw a path through places in order. Headline above the map.
- beforeafter: exactly 2 items: items[0] = before/old/myth, items[1] = after/new/reality. "label" = short tag
  (e.g. "1900", "Myth", "Without"), "display" = the state in <= 6 words. Optional "image_query" per item.
- On-screen numbers must match the spoken numbers exactly (same unit and rounding: say "fifty-two cents" -> show
  52 with suffix "¢", not 51.5%). Every number the narration stresses should appear on screen in that scene.
- Avoid text-only frames in the middle of the video: "statement" is for the hook-like turns only.
  If a scene's narration states a number, use "stat"; a contrast of two or more quantities/eras, use "compare"
  or "beforeafter"; a mechanism, use "diagram" (flow for 3+ steps); a place or route, use "map".
- Every hook/statement/outro/stat WITHOUT a photo gets a big animated pictogram: set "icon" to 1-3 concrete, drawable
  nouns, best first (e.g. "snowflake, thermometer", "popcorn", "dna", "ship, anchor", "banknote"). Pick the object
  that IS the idea of that scene, not a generic symbol. Give "icon" keywords even when you also set
  "image_query" (they are the backup if no good photo is found).
- Put photos where the subject is FIRST introduced (ideally the hook shows the real subject), not on abstract lines.
- Use 2-4 DIFFERENT visual scene types per short. Prefer diagram/map/beforeafter whenever they explain better than words.
- PHOTOS: you may set "image_query" on up to {max_images} scenes (hook preferred, also statement/beforeafter) when a
  real photo of a CONCRETE, photographable subject helps: an object, animal, place, machine, artifact, spacecraft.
  2-4 literal words ("red onion halves", "Hoover Dam aerial"). Photos beat icons for concrete subjects:
  use them on stat scenes too when the number is about a photographable thing. Never abstract ideas, never private people, never
  brands as the subject. Use "image_source": "nasa" only for space/astronomy subjects.
- Spell numbers in narration the way they should be SPOKEN (e.g. "two hundred thousand").
- Pick a theme that matches the mood: midnight (tech/space), ember (history/energy), mint (nature/biology),
  paper (economics/design/editorial), ultraviolet (mind/physics/weird).
- Title <= 60 chars, honest curiosity. 3-5 hashtags (no spaces). 8-15 search tags.
- sources: 1-3 credible URLs or citations backing the main claims.
"""

IDEATE = GUIDE + """
CONTENT PILLAR for this short: "{pillar}" (set "pillar" to exactly this).

{research}

AVOID these already-made topics (and close variants):
{avoid}

{perf}
{lessons}
{seed}
Produce ONE short as the structured output.
"""

FACTCHECK = """
You are a strict fact-checker and retention editor for a YouTube Shorts explainer.
Here is a scene spec as JSON:

{spec}

1. Verify every factual claim and number{web}. Fix anything false, exaggerated, or outdated.
   If the core premise is false or a myth, replace it with a true, equally surprising angle on the same topic.
2. Keep all structure rules: hook first (<= 12 words), outro last that loops back into the hook,
   total narration 85-125 words, headlines <= ~7 words, numbers in narration spelled as spoken.
3. LOCKSTEP AUDIT, scene by scene: remove any on-screen item (bar, list/timeline entry, label, number) the
   narration of that scene does not say; make every stressed spoken number appear on screen with the same
   rounding; make sure no scene shows a later scene's payoff.
4. HOOK: rewrite the hook headline as the strongest of 3 alternatives you consider (<= 5 words, concrete subject
   + tension, same claim as the spoken hook). Make sure the hook has an "image_query" for the real subject when
   it is photographable, and that photos sit on the scene where their subject is first named.
5. Tighten wording for retention. Keep the same JSON shape.
Return the corrected spec as the structured output.
""" + GUIDE


class ClaudeError(RuntimeError):
    pass


def claude_json(cfg, prompt: str, schema: dict, web: bool) -> dict:
    c = cfg.claude
    cmd = [c["binary"], "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(schema)]
    if c.get("model"):
        cmd += ["--model", c["model"]]
    if web:
        cmd += ["--allowedTools", "WebSearch,WebFetch"]
    cmd += ["--disallowedTools", "Bash,Edit,Write,NotebookEdit"]
    last = None
    for attempt in range(int(c.get("retries", 3))):
        try:
            with tempfile.TemporaryDirectory() as td:  # empty cwd: no project context leaks in
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=c.get("timeout_sec", 600), cwd=td)
            if r.returncode != 0:
                raise ClaudeError(f"claude exit {r.returncode}: {r.stderr[-500:] or r.stdout[-500:]}")
            out = json.loads(r.stdout)
            if out.get("is_error"):
                raise ClaudeError(f"claude error: {str(out.get('result'))[:500]}")
            data = out.get("structured_output")
            if data is None:
                data = _extract_json(out.get("result", ""))
            return data
        except (ClaudeError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            last = e
            wait = 30 * (attempt + 1) ** 2
            print(f"[claude] attempt {attempt + 1} failed: {e}; retrying in {wait}s")
            time.sleep(wait)
    raise ClaudeError(f"claude failed after retries: {last}")


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise json.JSONDecodeError("no json object in result", text, 0)
    return json.loads(text[s:e + 1])


def make_spec(cfg, avoid: list[str], perf: str = "", seed: str = "", pillar: str = "") -> dict:
    ch = cfg.channel
    web = bool(cfg.claude.get("research"))
    fmt = dict(series=ch["series_name"], niche=ch["niche"], audience=ch["audience"], tone=ch["tone"],
               max_images=int(cfg.get("images", {}).get("max_per_video", 5)))
    research = (
        "First use web search to find a fresh, surprising, well-documented idea in the niche and confirm its key "
        "facts with credible sources (encyclopedias, universities, agencies, reputable press)."
        if web else "Use only facts you are highly confident are true and well documented."
    )
    seed_txt = f"Topic seed for variety (optional to follow): {seed}\n" if seed else ""
    from .analytics import lessons_for_prompt
    from .insights import recent_problems_for_prompt
    prompt = IDEATE.format(**fmt, research=research, pillar=pillar,
                           lessons=lessons_for_prompt() + recent_problems_for_prompt(), avoid="\n".join(f"- {a}" for a in avoid) or "- (none yet)",
                           perf=perf, seed=seed_txt)
    spec = claude_json(cfg, prompt, SPEC_SCHEMA, web)
    if cfg.claude.get("fact_check"):
        prompt2 = FACTCHECK.format(spec=json.dumps(spec, indent=1), web=" using web search" if web else "", **fmt)
        spec = claude_json(cfg, prompt2, SPEC_SCHEMA, web)
    spec["pillar"] = pillar or spec.get("pillar", "")
    return normalize(spec, cfg)


REVISE = """
You are the editor fixing a YouTube Short that FAILED its quality check. Here is its scene spec JSON:

{spec}

Quality report (layout problems, narration mismatches where the text-to-speech misread words, viewer review):
{problems}

Rewrite the spec to fix every problem while keeping the topic, facts, sources and overall structure:
- layout overflow / overlap / tiny text: shorten the offending headline, labels or items (fewer, shorter words).
- narration mismatch: rephrase words the voice misreads (spell acronyms as spoken, write numbers as words,
  avoid unusual names or symbols).
- review issues: apply the suggested fixes; strengthen the hook if it scored low.
Photos: an existing "image" field is a downloaded photo. You may MOVE it to the scene where its subject first
appears (copy the exact path and its "image_query"), or drop it. To get a NEW photo, set "image_query" (2-4 literal
words) on that scene without an "image" field; it will be searched and vetted. Return the corrected spec as the
structured output.
""" + GUIDE


def revise(cfg, spec: dict, report: dict) -> dict:
    ch = cfg.channel
    fmt = dict(series=ch["series_name"], niche=ch["niche"], audience=ch["audience"], tone=ch["tone"],
               max_images=int(cfg.get("images", {}).get("max_per_video", 5)))
    problems = {k: report.get(k) for k in ("fails", "warns", "layout", "review")}
    if report.get("narration"):
        problems["narration_mismatches"] = report["narration"].get("mismatches")
    new = claude_json(cfg, REVISE.format(spec=json.dumps(spec, indent=1), problems=json.dumps(problems, indent=1), **fmt),
                      SPEC_SCHEMA, web=False)
    # only keep photo paths that really exist (the model may move or drop them, never invent them)
    from pathlib import Path
    for sc in new["scenes"]:
        if sc.get("image") and not Path(sc["image"]).exists():
            sc.pop("image")
    new["credits"] = spec.get("credits", [])
    new["pillar"] = spec.get("pillar", "")
    return normalize(new, cfg)


def choose_pillar(cfg, stats: dict[str, list[float]]) -> str:
    """Pick the next content pillar: mostly exploit pillars with higher avg % viewed, keep ~30% exploration."""
    pillars = list(cfg.channel.get("pillars", [])) or ["general"]
    rng = random.Random()
    if rng.random() < 0.3 or not stats:
        return rng.choice(pillars)
    scored = []
    for p in pillars:
        v = stats.get(p, [])
        mean = sum(v) / len(v) if len(v) >= 3 else 75.0  # optimistic prior for under-sampled pillars
        scored.append((max(1.0, mean) ** 2, p))
    total = sum(w for w, _ in scored)
    r = rng.random() * total
    for w, p in scored:
        r -= w
        if r <= 0:
            return p
    return scored[-1][1]


def normalize(spec: dict, cfg) -> dict:
    theme = cfg.video.get("theme", "auto")
    if theme != "auto":
        spec["theme"] = theme
    if spec.get("theme") not in THEMES:
        spec["theme"] = random.choice(THEMES)
    sc = spec["scenes"]
    if sc[0]["type"] != "hook":
        sc[0]["type"] = "hook"
    if sc[-1]["type"] != "outro":
        sc[-1]["type"] = "outro"
    for s in sc:
        s["narration"] = " ".join(s["narration"].split())
        t = s["type"]
        items = s.get("items") or []
        # downgrade visual scenes that lack the data they need, so the renderer never shows an empty frame
        if (t == "map" and not (s.get("places") or s.get("regions"))) or \
           (t == "diagram" and len(items) < 2) or (t == "beforeafter" and len(items) < 2) or \
           (t in ("compare", "list", "timeline") and len(items) < 2) or (t == "stat" and s.get("value") is None):
            s["type"] = "statement"
        if s["type"] == "diagram" and s.get("layout") not in ("flow", "cycle", "hub"):
            s["layout"] = "flow"
        if not s.get("headline") and s["type"] in ("hook", "statement", "outro"):
            s["headline"] = " ".join(s["narration"].split()[:6])
    spec["hashtags"] = ["#" + h.lstrip("#").replace(" ", "") for h in spec.get("hashtags", [])][:5]
    return spec
