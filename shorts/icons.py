"""Pictograms for text-only scenes, from Lucide (ISC license, ~2,300 line icons, bundled via npm).

The writer gives 1-3 keywords per scene ("icon"); if it doesn't, we fall back to strict exact matches on the
scene's emphasis/headline/narration words. The icon's SVG nodes are embedded in the scene so the renderer can draw
it stroke by stroke.
"""
import json
import re
from functools import lru_cache

from .config import ROOT

TEXT_SCENES = ("hook", "statement", "outro", "stat")

# words that would match an icon literally but carry no picture of the idea
STOP = set("""a an the and or but so of to in on at by for with from up down out over under again then once here there
when where why how all any both each few more most other some such no nor not only own same than too very can will just
is are was were be been being have has had do does did this that these those it its it's you your we our they their
i me my he she him her them what which who whom one two three four five six seven eight nine ten half first last
new old big small long short high low left right top bottom back way thing things really actually even still yet
never always every day days year years time times part parts make makes made get gets got keep keeps kept real
hidden why answer truth secret move moves moving work works lot lots zero none nothing nobody everyone
percent cents""".split())

# brand / crypto / app logos: only used when asked for by exact name, never via fuzzy tag matching
DENY_FUZZY = {"bitcoin", "github", "gitlab", "twitter", "facebook", "instagram", "youtube", "linkedin", "twitch",
              "slack", "figma", "framer", "codepen", "codesandbox", "dribbble", "chrome", "chromium", "trello", "pocket",
              "euro", "pound-sterling", "japanese-yen", "indian-rupee", "russian-ruble", "swiss-franc", "philippine-peso",
              "turkish-lira", "saudi-riyal", "badge-euro", "badge-pound-sterling", "badge-japanese-yen"}

# concept -> canonical icon (Lucide tag search alone picks odd ones, e.g. money -> euro)
PREFER = {"money": "banknote", "cash": "banknote", "price": "tag", "prices": "tag", "cost": "receipt", "costs": "receipt",
          "profit": "trending-up", "loss": "trending-down", "market": "store", "business": "briefcase", "bank": "landmark",
          "time": "clock", "energy": "zap", "power": "zap", "science": "flask-conical", "history": "landmark",
          "idea": "lightbulb", "space": "orbit", "planet": "earth", "world": "earth", "body": "person-standing",
          "study": "book-open", "law": "scale", "weather": "cloud-sun", "heat": "thermometer-sun", "cold": "snowflake",
          "ocean": "waves-horizontal", "sea": "waves-horizontal", "city": "building", "road": "route", "trade": "ship", "war": "swords",
          "food": "utensils", "health": "heart-pulse", "disease": "biohazard", "evolution": "dna", "gene": "dna",
          "nerve": "activity", "data": "chart-column", "growth": "sprout", "speed": "gauge", "light": "sun", "sound": "audio-lines",
          "winter": "snowflake", "summer": "sun", "rain": "cloud-rain", "storm": "cloud-lightning", "fire": "flame",
          "tears": "droplets", "water": "droplets", "chemical": "flask-conical", "chemicals": "flask-conical",
          "enzyme": "flask-conical", "gas": "wind", "air": "wind", "plant": "leaf", "tree": "tree-pine",
          "tower": "building", "skyscraper": "building", "building": "building", "bridge": "bridge",
          "engine": "cog", "coin": "coins", "nickel": "coins", "penny": "coins", "dime": "coins", "dollar": "dollar-sign", "machine": "cog", "train": "train-front", "railroad": "train-track", "clock": "clock"}


@lru_cache(maxsize=1)
def _db():
    base = ROOT / "node_modules" / "lucide-static"
    nodes = json.loads((base / "icon-nodes.json").read_text())
    tags = json.loads((base / "tags.json").read_text())
    by_tag: dict[str, list[str]] = {}
    for name, ts in tags.items():
        for t in ts:
            by_tag.setdefault(t.lower(), []).append(name)
    return nodes, tags, by_tag


def _stem(w: str) -> list[str]:
    w = re.sub(r"[^a-z\-]", "", w.lower())
    out = [w]
    for suf, rep in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ed", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            out.append(w[: -len(suf)] + rep)
    return [x for x in out if x]


def find(query: str, strict: bool = False) -> str | None:
    """Best Lucide icon name for a keyword phrase."""
    nodes, tags, by_tag = _db()
    q = query.lower().strip()
    if not q:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", q).strip("-")
    if slug in nodes:
        return slug
    words = [w for w in re.split(r"[\s,/]+", q) if w and w not in STOP]
    for w in words:
        if w in PREFER and PREFER[w] in nodes:
            return PREFER[w]
    for w in words:
        for s in _stem(w):
            if s in nodes:
                return s
    for w in words:
        for s in _stem(w):
            ok = [n for n in by_tag.get(s, []) if n not in DENY_FUZZY]
            if ok:
                return sorted(ok, key=len)[0]  # the shortest name is usually the canonical icon
    if strict:
        return None
    for w in words:  # loose: icon names that start with the word ("plane" -> "plane-takeoff")
        for s in _stem(w):
            cands = [n for n in nodes if n.startswith(s + "-") and n not in DENY_FUZZY]
            if cands:
                return sorted(cands, key=len)[0]
    return None


def resolve(spec: dict) -> None:
    """Attach icon_nodes to text-only scenes (no photo).
    Order: writer's icon keywords -> words of a photo search that failed -> headline words -> a default
    (statement/outro only; the hook never gets a generic symbol). Defaults never repeat; a matched icon may
    repeat if it isn't in the previous scene."""
    nodes, _, _ = _db()
    used: set[str] = set()
    prev = None
    for sc in spec["scenes"]:
        sc.pop("icon_nodes", None)
        sc.pop("icon_name", None)
        if sc["type"] not in TEXT_SCENES or sc.get("image"):
            prev = None
            continue
        matched = []
        if sc.get("icon"):  # the writer's own keywords: full search incl. Lucide tags
            matched += [find(kw) for kw in re.split(r"[,;]", sc["icon"])]
        if sc.get("image_query"):  # words of a photo search: exact names only (tags give "tower" -> pc-case)
            for w in sc["image_query"].lower().split():
                if len(w) >= 4 and w not in STOP:
                    matched += [PREFER.get(w)] + [x for x in _stem(w) if x in nodes]
        words = [re.sub(r"[^\w\-]", "", w.lower()) for w in [*sc.get("emphasis", []), *(sc.get("headline") or "").split()]]
        words = [w for w in words if len(w) >= 4 and w not in STOP]
        matched += [PREFER.get(w) for w in words] + [x for w in words for x in _stem(w) if x in nodes]
        matched = [m for m in matched if m and m in nodes]
        name = next((m for m in matched if m not in used), None) or next((m for m in matched if m != prev), None)
        if not name and sc["type"] in ("statement", "outro"):
            defaults = (["circle-question-mark"] if (sc.get("headline") or "").strip().endswith("?") else []) + \
                {"statement": ["lightbulb", "search", "eye", "sparkles"], "outro": ["repeat", "infinity"]}[sc["type"]]
            name = next((d for d in defaults if d in nodes and d not in used), None)
        prev = name
        if name:
            used.add(name)
            sc["icon_name"] = name
            sc["icon_nodes"] = nodes[name]
