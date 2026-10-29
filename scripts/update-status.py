#!/usr/bin/env python3
"""Refresh commit-activity + now-playing assets.

Outputs:
  1. assets/character.svg    — patches three small fields in place
       <circle id="status-dot">     dot color
       <text   id="status-push">    "last push · HH:MM JST · Nh ago"
       <text   id="status-text">    ONLINE / IDLE / AFK

  2. assets/productive.svg   — bar chart of commit activity
                                by JST bucket (morning / daytime / evening / night).

  3. assets/now-playing.svg  — anime + manga currently / favorite, with
                                priority chain: AniList → Jikan/MAL → data/now-playing.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER", "kidneyweakx")
ROOT = Path(__file__).resolve().parent.parent
CHARACTER_SVG    = ROOT / "assets" / "character.svg"
PRODUCTIVE_SVG   = ROOT / "assets" / "productive.svg"
NOW_PLAYING_SVG  = ROOT / "assets" / "now-playing.svg"
NOW_PLAYING_JSON = ROOT / "data"   / "now-playing.json"

JST = dt.timezone(dt.timedelta(hours=9), name="JST")
TZ_LABEL = "JST"

# Palette lifted from the avatar — keep in sync with assets/header.svg.
INK    = "#1b1923"   # hoodie
DUSK   = "#403b66"   # wall behind her
TRACK  = "#2a2836"
PAPER  = "#f3ece8"   # skin highlight
MUTED  = "#8a86a3"
LILAC  = "#c9c3e6"
BLUE   = "#3fb4d8"   # hair streak
PINK   = "#de5b94"   # sleeve stripe
SANS   = "ui-sans-serif, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, &quot;Hiragino Sans&quot;, &quot;Noto Sans JP&quot;, Helvetica, Arial, sans-serif"

ONLINE = ("ONLINE", "#6fbf73")
IDLE   = ("IDLE",   "#e2b25a")
AFK    = ("AFK",    MUTED)

BUCKETS = [
    ("Morning", "06–12", "morning", "#e2b25a"),
    ("Daytime", "12–18", "daytime", BLUE),
    ("Evening", "18–24", "evening", PINK),
    ("Night",   "00–06", "night",   "#9a8fe0"),
]

UA = f"{USER}-status-updater/1.0"


# ============================================================
#  GitHub events  (status dot + productive chart)
# ============================================================

def bucket_key(h: int) -> str:
    if   6 <= h < 12:  return "morning"
    elif 12 <= h < 18: return "daytime"
    elif 18 <= h < 24: return "evening"
    else:              return "night"


def fetch_events(user: str) -> list[dict]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"https://api.github.com/users/{user}/events/public?per_page=100",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"github api error: {exc.code} {exc.reason}", file=sys.stderr)
        return []
    except Exception as exc:
        print(f"github fetch failed: {exc}", file=sys.stderr)
        return []


def find_latest_push(events: list[dict]) -> dt.datetime | None:
    latest: dt.datetime | None = None
    for e in events:
        if e.get("type") not in ("PushEvent", "CreateEvent", "PullRequestEvent"):
            continue
        when = dt.datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if latest is None or when > latest:
            latest = when
    return latest


def aggregate_buckets(events: list[dict]) -> dict[str, int]:
    counts = {k: 0 for _, _, k, _ in BUCKETS}
    for e in events:
        if e.get("type") not in ("PushEvent", "PullRequestEvent"):
            continue
        when = dt.datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).astimezone(JST)
        counts[bucket_key(when.hour)] += 1
    return counts


def classify(latest: dt.datetime | None) -> tuple[tuple[str, str], str]:
    now = dt.datetime.now(dt.timezone.utc)
    if latest is None:
        return AFK, "no recent push"
    delta = now - latest
    h = delta.total_seconds() / 3600
    bucket = ONLINE if h < 6 else (IDLE if h < 24 else AFK)
    if h < 1:
        ago = f"{int(delta.total_seconds() // 60)}m ago"
    elif h < 48:
        ago = f"{int(h)}h ago"
    else:
        ago = f"{int(h // 24)}d ago"
    return bucket, f"last push · {latest.astimezone(JST):%H:%M} {TZ_LABEL} · {ago}"


def patch_character(status: str, color: str, push_str: str) -> bool:
    svg = CHARACTER_SVG.read_text(encoding="utf-8")
    new = svg
    new = re.sub(
        r'(<circle id="status-dot"[^/>]*fill=")[^"]*(")',
        rf'\g<1>{color}\g<2>', new, count=1,
    )
    new = re.sub(
        r'(<text id="status-push"[^>]*>)[^<]*(</text>)',
        rf'\g<1>{push_str}\g<2>', new, count=1,
    )
    new = re.sub(
        r'(<text id="status-text"[^>]*fill=")[^"]*(">)[^<]*(</text>)',
        rf'\g<1>{color}\g<2>{status}\g<3>', new, count=1,
    )
    if new == svg:
        return False
    CHARACTER_SVG.write_text(new, encoding="utf-8")
    return True


def render_productive_svg(
    counts: dict[str, int],
    latest: dt.datetime | None,
    updated_at: dt.datetime,
) -> str:
    total = sum(counts.values())
    max_c = max(counts.values()) if counts else 0
    # 360 wide like the avatar card; with now-playing (H_NOW) and a 12px gap
    # the right column lands exactly at the card's 422px.
    W, H = 360, 180
    BAR_X, BAR_W, BAR_H, ROW_GAP, Y0 = 130, 150, 10, 24, 58

    rows: list[str] = []
    for i, (label, rng, key, color) in enumerate(BUCKETS):
        c = counts.get(key, 0)
        pct = (c / max_c) if max_c else 0
        bar_w = max(int(BAR_W * pct), 6)
        pct_total = int(round(c / total * 100)) if total else 0
        y = Y0 + i * ROW_GAP
        rows.append(
f"""  <g transform="translate(0,{y})">
    <text x="24" y="10" font-size="12" font-weight="600" fill="{PAPER}">{label}</text>
    <text x="84" y="10" font-size="10" fill="{MUTED}">{rng}</text>
    <rect x="{BAR_X}" y="0" width="{BAR_W}" height="{BAR_H}" rx="5" fill="{TRACK}"/>
    <rect class="bar" style="animation-delay:{200 + i * 90}ms" x="{BAR_X}" y="0" width="{bar_w}" height="{BAR_H}" rx="5" fill="{color}"/>
    <text x="{W - 24}" y="10" font-size="11" font-weight="600" text-anchor="end" fill="{PAPER}">{c}<tspan fill="{MUTED}" font-weight="400" dx="5">{pct_total}%</tspan></text>
  </g>"""
        )

    push_str = (
        f"last push {latest.astimezone(JST):%H:%M} {TZ_LABEL}"
        if latest else "no recent push"
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="When I commit (JST)">
  <style><![CDATA[
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    .bar {{ transform-box: fill-box; transform-origin: left; animation: grow 900ms cubic-bezier(.22,1,.36,1) both; }}
    @media (prefers-reduced-motion: reduce) {{ .bar {{ animation: none; }} }}
  ]]></style>
  <g font-family="{SANS}">
  <rect width="{W}" height="{H}" rx="16" fill="{INK}"/>

  <text x="24" y="38" font-size="16" font-weight="700" fill="{PAPER}">When I commit</text>
  <text x="{W - 24}" y="38" font-size="10" text-anchor="end" fill="{MUTED}">{TZ_LABEL} · last {total} events</text>

""" + "\n".join(rows) + f"""

  <text x="24" y="{H - 14}" font-size="10" fill="{MUTED}">{push_str}</text>
  <text x="{W - 24}" y="{H - 14}" font-size="10" text-anchor="end" fill="{MUTED}">updated {updated_at.astimezone(JST):%m-%d %H:%M}</text>
  </g>
</svg>
"""


# ============================================================
#  Anime + Manga  (now-playing card)
# ============================================================
#
#  Priority chain per media type:
#    1. AniList MediaListCollection (status=CURRENT)
#    2. Jikan /users/<u>/userupdates  (recent activity, any status)
#    3. data/now-playing.json         (manual seed)
#
#  Favorites always come from JSON (both AniList & Jikan favorite endpoints
#  return empty for this account).
# ============================================================

def fetch_anilist(username: str, media_type: str) -> list[dict]:
    """media_type in {'ANIME', 'MANGA'}."""
    query = """
    query ($name: String, $type: MediaType) {
      MediaListCollection(userName: $name, type: $type, status: CURRENT) {
        lists {
          entries {
            progress
            media {
              title { romaji english native }
              episodes chapters siteUrl
            }
          }
        }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"name": username, "type": media_type}}).encode()
    req = urllib.request.Request(
        "https://graphql.anilist.co",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.load(resp)
    except Exception as exc:
        print(f"anilist {media_type} fetch failed: {exc}", file=sys.stderr)
        return []

    out: list[dict] = []
    collection = (payload.get("data") or {}).get("MediaListCollection") or {}
    for lst in collection.get("lists", []):
        for e in lst.get("entries", []):
            media = e.get("media") or {}
            title = (media.get("title") or {})
            display = title.get("english") or title.get("romaji") or title.get("native") or "?"
            total = media.get("episodes") or media.get("chapters")
            progress = e.get("progress", 0)
            sub = f"ep {progress}/{total}" if total else (f"ep {progress}" if progress else "")
            out.append({"title": display, "subtitle": sub, "url": media.get("siteUrl"), "src": "anilist"})
    return out


def fetch_jikan(username: str, kind: str) -> list[dict]:
    """kind in {'anime', 'manga'}. Returns recent updates filtered to that media type."""
    req = urllib.request.Request(
        f"https://api.jikan.moe/v4/users/{username}/userupdates",
        headers={"User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.load(resp)
    except Exception as exc:
        print(f"jikan {kind} fetch failed: {exc}", file=sys.stderr)
        return []

    out: list[dict] = []
    items = (payload.get("data") or {}).get(kind, []) or []
    for item in items:
        entry = item.get("entry") or {}
        title = entry.get("title") or "?"
        status = item.get("status") or ""
        seen   = item.get("episodes_seen") or item.get("chapters_read")
        total  = item.get("episodes_total") or item.get("chapters_total")
        if seen and total:
            sub = f"{status.lower()} · {seen}/{total}"
        elif status:
            sub = status.lower()
        else:
            sub = ""
        out.append({"title": title, "subtitle": sub, "url": entry.get("url"), "src": "mal"})
    return out


def load_now_playing_json() -> dict:
    if not NOW_PLAYING_JSON.exists():
        return {}
    try:
        return json.loads(NOW_PLAYING_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"reading {NOW_PLAYING_JSON.name} failed: {exc}", file=sys.stderr)
        return {}


H_NOW = 236      # now-playing height; 236 + 180 productive + ~6px inline gap ≈ 422 card
CURRENT_CAP = 1  # keep card compact — show favorite + 1 current per section


def resolve_section(
    json_section: dict,
    anilist_entries: list[dict],
    jikan_entries: list[dict],
) -> dict:
    """Build {favorite, current[], src} for one media type using the priority chain."""
    if anilist_entries:
        current, src = anilist_entries[:CURRENT_CAP], "anilist"
    elif jikan_entries:
        current, src = jikan_entries[:CURRENT_CAP], "mal"
    else:
        current = [
            {"title": it.get("title", "?"), "subtitle": it.get("subtitle", ""), "src": "json"}
            for it in (json_section.get("current") or [])
        ][:CURRENT_CAP]
        src = "json"
    return {
        "favorite": json_section.get("favorite"),
        "current": current,
        "src": src,
    }


def escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def render_now_playing_svg(
    anime: dict,
    manga: dict,
    updated_at: dt.datetime,
) -> str:
    W = 360
    lines: list[str] = []

    def header(y: int, label: str, src: str) -> str:
        return (
            f'<text x="24" y="{y}" font-size="11" font-weight="700" letter-spacing="1.5" fill="{LILAC}">{label}</text>'
            f'<text x="{W-24}" y="{y}" font-size="10" text-anchor="end" fill="{MUTED}">via {src}</text>'
        )

    def row(y: int, color: str, mark: str, title: str, subtitle: str) -> str:
        title = escape_xml(truncate(title, 34))
        out = (
            f'<rect x="24" y="{y-10}" width="3" height="{25 if subtitle else 13}" rx="1.5" fill="{color}"/>'
            f'<text x="36" y="{y}" font-size="13" font-weight="600" fill="{PAPER}">{title}'
            f'<tspan fill="{MUTED}" font-size="10" font-weight="400" dx="6">{mark}</tspan></text>'
        )
        if subtitle:
            out += f'<text x="36" y="{y+14}" font-size="10.5" fill="{MUTED}">{escape_xml(truncate(subtitle, 44))}</text>'
        return out

    def section(y: int, label: str, data: dict, color: str) -> int:
        lines.append(header(y, label, data["src"] if data.get("current") else "json"))
        y += 24
        if data.get("favorite"):
            fav = data["favorite"]
            lines.append(row(y, color, "fav", fav["title"], fav.get("subtitle", "")))
            y += 34
        for it in data.get("current", []):
            lines.append(row(y, BLUE, "now", it["title"], it.get("subtitle", "")))
            y += 34
        return y

    y = section(66, "ANIME", anime, PINK)
    lines.append(f'<line x1="24" y1="{y - 8}" x2="{W-24}" y2="{y - 8}" stroke="{TRACK}"/>')
    y = section(y + 12, "MANGA", manga, PINK)

    # Fixed height keeps the right column level with the avatar card;
    # grows only if both media types have a current entry.
    H = max(H_NOW, y + 4)
    body = "\n    ".join(lines)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Now watching and reading">
  <style><![CDATA[
    @keyframes in {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
    .body {{ animation: in 600ms cubic-bezier(.22,1,.36,1) 150ms both; }}
    @media (prefers-reduced-motion: reduce) {{ .body {{ animation: none; }} }}
  ]]></style>
  <g font-family="{SANS}">
  <rect width="{W}" height="{H}" rx="16" fill="{INK}"/>
  <text x="24" y="38" font-size="16" font-weight="700" fill="{PAPER}">Now watching</text>
  <text x="{W-24}" y="38" font-size="10" text-anchor="end" fill="{MUTED}">updated {updated_at.astimezone(JST):%H:%M} {TZ_LABEL}</text>
  <g class="body">
    {body}
  </g>
  </g>
</svg>
"""


# ============================================================
#  Main
# ============================================================

def main() -> int:
    events = fetch_events(USER)
    latest = find_latest_push(events)
    counts = aggregate_buckets(events)
    (status, color), push_str = classify(latest)

    changed_char = patch_character(status, color, push_str)

    now = dt.datetime.now(dt.timezone.utc)
    new_prod = render_productive_svg(counts, latest, now)
    existing = PRODUCTIVE_SVG.read_text(encoding="utf-8") if PRODUCTIVE_SVG.exists() else ""
    changed_prod = new_prod != existing
    if changed_prod:
        PRODUCTIVE_SVG.write_text(new_prod, encoding="utf-8")

    # ---- now playing ----
    json_data = load_now_playing_json()
    al_anime = fetch_anilist(USER, "ANIME")
    al_manga = fetch_anilist(USER, "MANGA")
    jk_anime = fetch_jikan(USER, "anime") if not al_anime else []
    jk_manga = fetch_jikan(USER, "manga") if not al_manga else []

    anime = resolve_section(json_data.get("anime") or {}, al_anime, jk_anime)
    manga = resolve_section(json_data.get("manga") or {}, al_manga, jk_manga)

    new_np = render_now_playing_svg(anime, manga, now)
    existing_np = NOW_PLAYING_SVG.read_text(encoding="utf-8") if NOW_PLAYING_SVG.exists() else ""
    changed_np = new_np != existing_np
    if changed_np:
        NOW_PLAYING_SVG.parent.mkdir(parents=True, exist_ok=True)
        NOW_PLAYING_SVG.write_text(new_np, encoding="utf-8")

    print(f"status:   {status} · {push_str}")
    print(f"buckets:  {counts}")
    print(f"anime src: {anime['src']} · {len(anime.get('current') or [])} current")
    print(f"manga src: {manga['src']} · {len(manga.get('current') or [])} current")
    print(f"character.svg  changed: {changed_char}")
    print(f"productive.svg changed: {changed_prod}")
    print(f"now-playing.svg changed: {changed_np}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
