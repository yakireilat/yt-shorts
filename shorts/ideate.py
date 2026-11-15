"""Step 1+2: topic research, script + scene spec, fact-check — via the Claude CLI (your subscription)."""
import json
import random
import subprocess
import tempfile
import time

THEMES = ["midnight", "ember", "mint", "paper", "ultraviolet"]

SCENE_TYPES = ["hook", "statement", "stat", "compare", "list", "timeline", "outro"]

SPEC_SCHEMA = {
    "type": "object",
    "required": ["topic", "title", "description", "hashtags", "tags", "theme", "sources", "scenes"],
    "properties": {
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
                            },
                        },
                    },
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
- Last scene is type "outro": a one-line takeaway that ALSO flows naturally back into the hook sentence
  when the video loops (seamless loop). No "like and subscribe".
- Headlines: max ~7 words, punchy, not a copy of the narration. "emphasis" = 1-2 words from that headline.
- compare: 2-4 items with numeric "value" (same unit) and "display" (formatted, e.g. "1,200 km/h").
- list: 2-4 items with short "label" (<= 5 words).
- timeline: 2-5 items, "label" = year/date, "display" = what happened (<= 6 words).
- stat: "value" numeric, plus prefix/suffix/decimals and a short "label".
- Spell numbers in narration the way they should be SPOKEN (e.g. "two hundred thousand").
- Pick a theme that matches the mood: midnight (tech/space), ember (history/energy), mint (nature/biology),
  paper (economics/design/editorial), ultraviolet (mind/physics/weird).
- Title <= 60 chars, honest curiosity. 3-5 hashtags (no spaces). 8-15 search tags.
- sources: 1-3 credible URLs or citations backing the main claims.
"""

IDEATE = GUIDE + """
{research}

AVOID these already-made topics (and close variants):
{avoid}

{perf}
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
3. Tighten wording for retention. Keep the same JSON shape.
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


def make_spec(cfg, avoid: list[str], perf: str = "", seed: str = "") -> dict:
    ch = cfg.channel
    web = bool(cfg.claude.get("research"))
    fmt = dict(series=ch["series_name"], niche=ch["niche"], audience=ch["audience"], tone=ch["tone"])
    research = (
        "First use web search to find a fresh, surprising, well-documented idea in the niche and confirm its key "
        "facts with credible sources (encyclopedias, universities, agencies, reputable press)."
        if web else "Use only facts you are highly confident are true and well documented."
    )
    seed_txt = f"Topic seed for variety (optional to follow): {seed}\n" if seed else ""
    prompt = IDEATE.format(**fmt, research=research, avoid="\n".join(f"- {a}" for a in avoid) or "- (none yet)",
                           perf=perf, seed=seed_txt)
    spec = claude_json(cfg, prompt, SPEC_SCHEMA, web)
    if cfg.claude.get("fact_check"):
        prompt2 = FACTCHECK.format(spec=json.dumps(spec, indent=1), web=" using web search" if web else "", **fmt)
        spec = claude_json(cfg, prompt2, SPEC_SCHEMA, web)
    return normalize(spec, cfg)


SEEDS = [
    "everyday objects", "the human body", "transport & aviation", "food chemistry", "architecture",
    "money & economics", "internet & computers", "animals' weird engineering", "space", "history's small details",
    "materials science", "weather", "language & words", "sports physics", "design decisions we never notice",
]


def random_seed() -> str:
    return random.choice(SEEDS)


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
        if not s.get("headline") and s["type"] in ("hook", "statement", "outro"):
            s["headline"] = " ".join(s["narration"].split()[:6])
    spec["hashtags"] = ["#" + h.lstrip("#").replace(" ", "") for h in spec.get("hashtags", [])][:5]
    return spec
