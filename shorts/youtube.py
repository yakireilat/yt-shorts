"""Steps 8+9: YouTube upload (Data API v3) and stats (Data + Analytics API). Free; uses your OAuth app."""
import datetime as dt
import time
from pathlib import Path

from .config import rel

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _creds(cfg, interactive=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    tok = rel(cfg.publish.token)
    creds = Credentials.from_authorized_user_file(str(tok), SCOPES) if tok.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        tok.write_text(creds.to_json())
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("No valid YouTube token. Run: python -m shorts auth")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(rel(cfg.publish.client_secret)), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        tok.parent.mkdir(parents=True, exist_ok=True)
        tok.write_text(creds.to_json())
    return creds


def auth(cfg):
    _creds(cfg, interactive=True)
    print("YouTube auth OK ->", rel(cfg.publish.token))


def _yt(cfg, api="youtube", ver="v3"):
    from googleapiclient.discovery import build
    return build(api, ver, credentials=_creds(cfg), cache_discovery=False)


def description(spec, cfg):
    parts = [spec.get("description", "").strip()]
    if spec.get("sources"):
        parts.append("Sources:\n" + "\n".join(f"• {s}" for s in spec["sources"][:3]))
    parts.append(" ".join(spec.get("hashtags", [])))
    return "\n\n".join(p for p in parts if p)[:4900]


def upload(cfg, spec, path: Path, publish_at: dt.datetime | None = None) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    p = cfg.publish
    lang = cfg.channel.get("language", "en-us").split("-")[0]
    status = {
        "privacyStatus": "private" if publish_at else p.get("privacy", "public"),
        "selfDeclaredMadeForKids": bool(p.get("made_for_kids", False)),
        "containsSyntheticMedia": bool(p.get("synthetic_media", True)),
    }
    if publish_at:
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    body = {
        "snippet": {
            "title": spec["title"][:100],
            "description": description(spec, cfg),
            "tags": spec.get("tags", [])[:15],
            "categoryId": str(p.get("category_id", "27")),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": status,
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = _yt(cfg).videos().insert(part="snippet,status", body=body, media_body=media)
    resp, backoff = None, 5
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"  upload {int(st.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and backoff < 300:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
    return resp["id"]


def fetch_stats(cfg, ids: list[str]) -> dict:
    """Returns {video_id: {...}} using Data API statistics + Analytics retention metrics."""
    out = {}
    yt = _yt(cfg)
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute()
        for it in r.get("items", []):
            s = it["statistics"]
            out[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                             "comments": int(s.get("commentCount", 0)), "avg_view_pct": None,
                             "avg_view_sec": None, "subs_gained": None}
    try:
        ya = _yt(cfg, "youtubeAnalytics", "v2")
        for i in range(0, len(ids), 50):
            r = ya.reports().query(
                ids="channel==MINE", startDate="2020-01-01", endDate=dt.date.today().isoformat(),
                metrics="views,averageViewPercentage,averageViewDuration,subscribersGained",
                dimensions="video", filters="video==" + ",".join(ids[i:i + 50]),
            ).execute()
            for row in r.get("rows", []) or []:
                vid, _, pct, sec, subs = row
                if vid in out:
                    out[vid].update(avg_view_pct=pct, avg_view_sec=sec, subs_gained=subs)
    except Exception as e:  # analytics can lag 24-48h; never block the pipeline on it
        print("[analytics] skipped:", e)
    return out
