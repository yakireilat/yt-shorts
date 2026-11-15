import json
import sqlite3
import time
from .config import rel

SCHEMA = """
create table if not exists videos(
  run_id text primary key,
  created_at real,
  topic text,
  title text,
  spec text,
  path text,
  duration real,
  qa_ok integer,
  qa_notes text,
  status text,            -- rendered | queued | uploaded | failed | skipped
  youtube_id text,
  uploaded_at real
);
create table if not exists stats(
  youtube_id text,
  fetched_at real,
  views integer,
  likes integer,
  comments integer,
  avg_view_pct real,
  avg_view_sec real,
  subs_gained integer,
  primary key(youtube_id, fetched_at)
);
"""


def connect(cfg):
    path = rel(cfg.paths.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def recent_topics(con, n=150):
    rows = con.execute("select topic, title from videos order by created_at desc limit ?", (n,))
    return [f"{r['topic']} | {r['title']}" for r in rows]


def insert_video(con, run_id, spec, path, duration, qa_ok, qa_notes, status):
    con.execute(
        "insert or replace into videos(run_id, created_at, topic, title, spec, path, duration, qa_ok, qa_notes, status)"
        " values(?,?,?,?,?,?,?,?,?,?)",
        (run_id, time.time(), spec.get("topic"), spec.get("title"), json.dumps(spec), str(path),
         duration, int(qa_ok), "; ".join(qa_notes), status),
    )
    con.commit()


def uploads_last_24h(con):
    return con.execute(
        "select count(*) from videos where status='uploaded' and uploaded_at > ?", (time.time() - 86400,)
    ).fetchone()[0]


def performance_summary(con, k=5):
    """Best and worst performers by avg view %, for the ideation prompt."""
    q = """
    select v.title, v.topic, s.views, s.avg_view_pct from videos v
    join stats s on s.youtube_id = v.youtube_id
    where s.fetched_at = (select max(fetched_at) from stats s2 where s2.youtube_id = s.youtube_id)
      and s.views >= 50
    order by s.avg_view_pct desc
    """
    rows = [dict(r) for r in con.execute(q)]
    if len(rows) < 4:
        return ""
    fmt = lambda r: f"- \"{r['title']}\" ({r['views']} views, {r['avg_view_pct']:.0f}% avg viewed)"
    best = "\n".join(fmt(r) for r in rows[:k])
    worst = "\n".join(fmt(r) for r in rows[-k:])
    return f"Best performing so far:\n{best}\n\nWorst performing so far:\n{worst}\n"


def pillar_stats(con) -> dict[str, list[float]]:
    """avg % viewed of each uploaded short, grouped by content pillar (latest stats snapshot)."""
    q = """
    select json_extract(v.spec, '$.pillar') as pillar, s.avg_view_pct as pct from videos v
    join stats s on s.youtube_id = v.youtube_id
    where s.fetched_at = (select max(fetched_at) from stats s2 where s2.youtube_id = s.youtube_id)
      and s.avg_view_pct is not null and s.views >= 50
    """
    out: dict[str, list[float]] = {}
    for r in con.execute(q):
        if r["pillar"]:
            out.setdefault(r["pillar"], []).append(float(r["pct"]))
    return out
