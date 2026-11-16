"""Real photos without a GPU: search open-licensed image libraries, let Claude visually pick (or reject), credit them.

Sources (no API keys needed):
  * Openverse (api.openverse.org): 800M+ CC/public-domain images aggregated from Wikimedia Commons, Flickr CC,
    Smithsonian, the Met, museums, NASA on Flickr, ... filtered to commercial-safe licenses.
  * NASA Image and Video Library (images-api.nasa.gov): public-domain space imagery.
"""
import io
import json
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

UA = "shorts-machine/0.2 (open-source educational video generator)"
S = requests.Session()
S.headers["User-Agent"] = UA


def _get(url, **kw):
    r = S.get(url, timeout=kw.pop("timeout", 25), **kw)
    r.raise_for_status()
    return r


def search_openverse(q: str, licenses: str, min_w: int, n=12) -> list[dict]:
    params = {"q": q, "license": licenses, "page_size": 20, "mature": "false"}
    r = _get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)).json()
    out = []
    for it in r.get("results", []):
        if (it.get("width") or 0) < min_w or it.get("unstable__sensitivity"):
            continue
        lic = f"CC {it['license'].upper()} {it.get('license_version') or ''}".strip()
        if it["license"] in ("cc0", "pdm"):
            lic = "Public domain" if it["license"] == "pdm" else "CC0"
        out.append({
            "url": it["url"], "thumb": it["thumbnail"], "w": it.get("width"), "h": it.get("height"),
            "creator": it.get("creator") or "",
            "title": it.get("title") or "", "credit": f"\"{it.get('title') or 'Untitled'}\" by {it.get('creator') or 'unknown'} ({lic}), "
                                                    f"{it.get('foreign_landing_url') or ''}".strip(),
        })
        if len(out) >= n:
            break
    return out


def search_nasa(q: str, n=6) -> list[dict]:
    r = _get("https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": "image"})).json()
    out = []
    for it in r["collection"]["items"][:n]:
        d = it["data"][0]
        thumb = next((l["href"] for l in it.get("links", []) if l.get("render") == "image"), None)
        if not thumb:
            continue
        base = thumb.rsplit("~", 1)[0]
        out.append({"url": [base + "~large.jpg", base + "~orig.jpg", thumb], "thumb": thumb, "title": d.get("title", ""),
                    "creator": "nasa-" + str(d.get("nasa_id", ""))[:3],
                    "credit": f"\"{d.get('title', '')}\" — NASA ({d.get('nasa_id')}), public domain"})
    return out


SPACEY = re.compile(r"\b(satellite|rocket|orbit|space|planet|moon|mars|jupiter|saturn|galaxy|nebula|astronaut|"
                    r"telescope|iss|shuttle|comet|asteroid|sun|solar|nasa|launch)\b", re.I)


def search_wikimedia(q: str, licenses: str, min_w: int, n=10) -> list[dict]:
    """Wikimedia Commons file search (often better than Openverse for named objects and places)."""
    allow_sa = "by-sa" in licenses
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {q}",
              "gsrnamespace": 6, "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 600}
    r = _get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)).json()
    out = []
    for page in sorted((r.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99)):
        ii = (page.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = re.sub(r"<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", "")).strip()
        ok = lic.lower().startswith(("cc0", "public domain", "pd")) or re.match(r"cc by \d", lic.lower()) or \
            (allow_sa and lic.lower().startswith("cc by-sa"))
        if not ok or (ii.get("width") or 0) < min_w:
            continue
        artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "unknown")).strip()[:60]
        title = page.get("title", "").removeprefix("File:").rsplit(".", 1)[0]
        out.append({"url": ii.get("url"), "thumb": ii.get("thumburl"), "w": ii.get("width"), "h": ii.get("height"),
                    "title": title, "creator": artist,
                    "credit": f"\"{title}\" by {artist} ({lic}), {ii.get('descriptionurl', '')}".strip()})
        if len(out) >= n:
            break
    return out


def gather(q: str, src: str, licenses: str, min_w: int, n: int = 9) -> list[dict]:
    """Candidates from every source with simplified-query fallbacks; max 2 per creator, no duplicates."""
    words = q.split()
    variants = [q] + ([" ".join(words[:2]), " ".join(words[-2:])] if len(words) > 2 else []) + \
        ([words[-1]] if len(words) == 2 else [])
    pools = []
    for v in dict.fromkeys(variants):
        for fn in ([lambda x: search_nasa(x)] if src == "nasa" or SPACEY.search(v) else []) + \
                [lambda x: search_openverse(x, licenses, min_w, 12), lambda x: search_wikimedia(x, licenses, min_w)]:
            try:
                pools.append(fn(v))
            except Exception as e:  # one source down (rate limit, outage) must not stop the others
                print(f"  images: a source failed for '{v}': {str(e)[:80]}")
        if sum(map(len, pools)) >= 3 * n:
            break
    out, seen, per_creator = [], set(), {}
    for i in range(max((len(p) for p in pools), default=0)):  # round-robin across sources for variety
        for p in pools:
            if i >= len(p):
                continue
            c = p[i]
            key = (c.get("title") or "").lower().strip()[:40] or c["thumb"]
            who = (c.get("creator") or "?").lower()
            if c["thumb"] in seen or key in seen or per_creator.get(who, 0) >= 2:
                continue
            seen.update({c["thumb"], key})
            per_creator[who] = per_creator.get(who, 0) + 1
            out.append(c)
            if len(out) >= n:
                return out
    return out


def _load(url_or_list, max_side=1600) -> Image.Image | None:
    for u in url_or_list if isinstance(url_or_list, list) else [url_or_list]:
        try:
            im = Image.open(io.BytesIO(_get(u, timeout=40).content))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_side, max_side))
            return im
        except Exception:
            continue
    return None


def _tone(im: Image.Image) -> Image.Image:
    """Lift dark or flat photos (phones show them small and over a dark UI): autocontrast + brighten if dim."""
    from PIL import ImageEnhance, ImageStat
    out = ImageOps.autocontrast(im, cutoff=1)
    lum = ImageStat.Stat(out.convert("L")).mean[0]
    if lum < 105:
        out = ImageEnhance.Brightness(out).enhance(min(1.45, 115 / max(lum, 40)))
    return ImageEnhance.Color(out).enhance(1.08)


def _sheet(thumbs: list[Image.Image | None], path: Path):
    """3x3 numbered contact sheet that Claude looks at."""
    cell = 400
    sheet = Image.new("RGB", (cell * 3, cell * 3), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
    for i, im in enumerate(thumbs[:9]):
        x, y = (i % 3) * cell, (i // 3) * cell
        if im is not None:
            t = ImageOps.fit(im, (cell - 8, cell - 8))
            sheet.paste(t, (x + 4, y + 4))
        draw.rectangle([x + 8, y + 8, x + 78, y + 78], fill=(0, 0, 0))
        draw.text((x + 22, y + 10), str(i), fill=(255, 255, 0), font=font)
    sheet.save(path, quality=85)


PICK_SCHEMA = {
    "type": "object", "required": ["picks"],
    "properties": {"picks": {"type": "array", "items": {
        "type": "object", "required": ["slot", "index"],
        "properties": {"slot": {"type": "integer"}, "index": {"type": "integer"}, "why": {"type": "string"},
                       "backups": {"type": "array", "items": {"type": "integer"},
                                   "description": "other acceptable indices, best first (used if the pick fails to download)"},
                       "retry_query": {"type": "string", "description": "if index is -1: a better 1-3 word search"}}}}},
}

PICK_PROMPT = """You are the photo editor for a premium educational YouTube Short (vertical 9:16; the photo is shown
full-width in the top half with a slow zoom and the headline below it).
For each slot below, use the Read tool to look at its contact sheet (numbered thumbnails 0-8) and pick the best
image index, or -1 if none is good enough.

A good pick: clearly and literally shows the subject, is sharp, BRIGHT and high-contrast (dark, hazy or
muddy shots read badly on phones; text sits on top of the photo), works when cropped to the
central area, and has NO watermark, NO big text/logos, NO recognizable private person, nothing gory or misleading.
If in doubt, choose -1: a missing photo is fine, a wrong photo is not.
Also list "backups": other acceptable indices, best first (empty if none).
When you choose -1, give "retry_query": a simpler, more literal 1-3 word search likely to find the subject
(e.g. "onion" instead of "cut onion halves").

{slots}
Return the structured output.
"""


def _claude_pick(cfg, slots: list[dict], sheets_dir: Path) -> dict[int, int]:
    c = cfg.claude
    lines = "\n".join(f"Slot {s['slot']}: subject \"{s['query']}\" — scene says: \"{s['context']}\" — sheet: {s['sheet']}"
                      for s in slots)
    cmd = [c["binary"], "-p", PICK_PROMPT.format(slots=lines), "--output-format", "json",
           "--json-schema", json.dumps(PICK_SCHEMA), "--allowedTools", "Read", "--add-dir", str(sheets_dir),
           "--disallowedTools", "Bash,Edit,Write,WebSearch,WebFetch"]
    if c.get("model"):
        cmd += ["--model", c["model"]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=c.get("timeout_sec", 600), cwd=sheets_dir)
    out = json.loads(r.stdout)
    data = out.get("structured_output") or {}
    return {p["slot"]: ([p["index"], *p.get("backups", [])] if p["index"] >= 0 else [-1], p.get("retry_query") or "")
            for p in data.get("picks", [])}


def resolve(cfg, spec: dict, outdir: Path):
    """Attach `image` paths to scenes/items that requested a photo and record credits in spec['credits']."""
    ic = cfg.get("images", {})
    licenses, min_w = ic.get("licenses", "cc0,pdm,by"), int(ic.get("min_width", 1000))
    budget = int(ic.get("max_per_video", 3))
    targets = []  # (holder dict, query, source, context)
    have = lambda h: bool(h.get("image")) and Path(h["image"]).exists()  # rebuilds reuse photos already fetched
    for sc in spec["scenes"]:
        if sc["type"] == "beforeafter":
            for it in (sc.get("items") or [])[:2]:
                if it.get("image_query") and not have(it):
                    targets.append((it, it["image_query"], sc.get("image_source", "openverse"), sc["narration"]))
        elif sc.get("image_query") and not have(sc) and sc["type"] in ("hook", "statement", "outro", "stat"):
            targets.append((sc, sc["image_query"], sc.get("image_source", "openverse"), sc["narration"]))
    targets = targets[: budget + 1]
    if not targets:
        return
    imgdir = outdir / "img"
    imgdir.mkdir(exist_ok=True)
    cands, picks = {}, {}
    queries = {k: q for k, (_, q, _, _) in enumerate(targets)}
    for rnd in range(2):  # round 2 retries rejected slots with Claude's better query
        slots = []
        for k, q in queries.items():
            holder, _, src, ctx = targets[k]
            found = gather(q, src, licenses, min_w)
            thumbs = [_load(f["thumb"], 600) for f in found]
            found = [f for f, t in zip(found, thumbs) if t is not None]
            thumbs = [t for t in thumbs if t is not None]
            if not found:
                continue
            sheet = imgdir / f"sheet{k}_{rnd}.jpg"
            _sheet(thumbs, sheet)
            cands[k] = found
            slots.append({"slot": k, "query": q, "context": ctx, "sheet": str(sheet)})
        if not slots:
            break
        got = _claude_pick(cfg, slots, imgdir) if ic.get("vision_check", True) else {s["slot"]: ([0, 1, 2], "") for s in slots}
        queries = {}
        for k, (ranked, retry) in got.items():
            idx = ranked[0]
            if idx >= 0:
                picks[k] = (ranked, dict(enumerate(cands.get(k, []))))
            elif retry and rnd == 0 and retry.lower() != targets[k][1].lower():
                queries[k] = retry
        if not queries:
            break
    credits, used = [], 0
    for k, (ranked, pool) in sorted(picks.items()):
        if used >= budget:
            break
        cand = im = None
        for idx in ranked:  # the pick first, then Claude's approved backups
            if idx in pool:
                im = _load(pool[idx]["url"])
                if im is not None and im.width >= 700:
                    cand = pool[idx]
                    break
                print(f"  images: slot {k} candidate {idx} download failed/too small, trying backup")
        if cand is None:
            continue
        p = imgdir / f"photo{k}.jpg"
        _tone(im).save(p, quality=90)
        targets[k][0]["image"] = str(p.resolve())
        credits.append(cand["credit"])
        used += 1
    spec["credits"] = list(dict.fromkeys([*spec.get("credits", []), *credits]))
    print(f"  images: {used} photo(s) used")
