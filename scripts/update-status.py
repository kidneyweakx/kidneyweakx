#!/usr/bin/env python3
"""Refresh commit-activity + now-playing assets.

Outputs:
  1. assets/character.svg    — patches three small fields in place
       <circle id="status-dot">     dot color
       <text   id="status-push">    "last push · HH:MM JST · Nh ago"
       <text   id="status-text">    ONLINE / IDLE / AFK

  2. assets/productive.svg   — cyberpunk bar chart of commit activity
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

ONLINE = ("ONLINE", "#39ff14")
IDLE   = ("IDLE",   "#ffb700")
AFK    = ("AFK",    "#888888")

BUCKETS = [
    ("MORNING", "06-12", "morning", "#ffb700"),
    ("DAYTIME", "12-18", "daytime", "#00f0ff"),
    ("EVENING", "18-24", "evening", "#ff79c6"),
    ("NIGHT",   "00-06", "night",   "#b026ff"),
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
    BAR_X, BAR_W, BAR_H, ROW_GAP, Y0 = 210, 290, 18, 32, 70

    rows: list[str] = []
    for i, (label, rng, key, color) in enumerate(BUCKETS):
        c = counts.get(key, 0)
        pct = (c / max_c) if max_c else 0
        bar_w = max(int(BAR_W * pct), (4 if c == 0 else 8))
        pct_total = int(round(c / total * 100)) if total else 0
        y = Y0 + i * ROW_GAP
        rows.append(
f"""    <g transform="translate(0,{y})">
      <text x="24" y="14" font-family="ui-monospace, monospace" font-size="11" fill="#00f0ff">▸ {label}</text>
      <text x="108" y="14" font-family="ui-monospace, monospace" font-size="9"  fill="#5a6275">{rng} JST</text>
      <rect x="{BAR_X}" y="3" width="{BAR_W}" height="{BAR_H}" rx="3" fill="#0a0a1a" stroke="#1a1a2e" stroke-width="1"/>
      <rect x="{BAR_X}" y="3" width="{bar_w}" height="{BAR_H}" rx="3" fill="{color}" opacity="0.9" filter="url(#glow)"/>
      <text x="540" y="14" font-family="ui-monospace, monospace" font-size="11" text-anchor="end" fill="#e8f7ff">{c}</text>
      <text x="582" y="14" font-family="ui-monospace, monospace" font-size="9"  text-anchor="end" fill="#5a6275">{pct_total}%</text>
    </g>"""
        )

    push_str = (
        f"last push · {latest.astimezone(JST):%H:%M} {TZ_LABEL}"
        if latest else "no recent push"
    )

    return (
"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 230" width="600" height="230" role="img" aria-label="Productive Time JST">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#1a0033"/>
      <stop offset="100%" stop-color="#000814"/>
    </linearGradient>
    <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M20 0 H0 V20" fill="none" stroke="#00f0ff" stroke-opacity="0.05"/>
    </pattern>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <style><![CDATA[
      @keyframes bracket { 0%, 100% { stroke-opacity: 0.4; } 50% { stroke-opacity: 1; } }
      .bracket { animation: bracket 2.2s ease-in-out infinite; }
    ]]></style>
  </defs>

  <rect width="600" height="230" rx="14" fill="url(#bg)"/>
  <rect width="600" height="230" rx="14" fill="url(#grid)"/>
  <rect width="600" height="230" rx="14" fill="none" stroke="#00f0ff" stroke-opacity="0.55" stroke-width="1.2"/>

  <g class="bracket" stroke="#00f0ff" stroke-width="1.5" fill="none">
    <polyline points="14,26 14,14 26,14"/>
    <polyline points="574,14 586,14 586,26"/>
    <polyline points="14,204 14,216 26,216"/>
    <polyline points="574,216 586,216 586,204"/>
  </g>

  <text x="24"  y="36" font-family="ui-monospace, monospace" font-size="13" font-weight="700" fill="#00f0ff">▸ PRODUCTIVE TIME · JST</text>
  <text x="580" y="36" font-family="ui-monospace, monospace" font-size="10" text-anchor="end" fill="#888">sample · """ + str(total) + """ events</text>

  <line x1="24" y1="52" x2="580" y2="52" stroke="#00f0ff" stroke-opacity="0.3"/>

""" + "\n".join(rows) + """

  <line x1="24" y1="200" x2="580" y2="200" stroke="#00f0ff" stroke-opacity="0.2"/>
  <text x="24"  y="218" font-family="ui-monospace, monospace" font-size="9" fill="#5a6275">▸ """ + push_str + """</text>
  <text x="580" y="218" font-family="ui-monospace, monospace" font-size="9" text-anchor="end" fill="#5a6275">updated · """ + f"{updated_at.astimezone(JST):%Y-%m-%d %H:%M} {TZ_LABEL}" + """</text>
</svg>
"""
    )


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
    H = 200
    ROW_FAV = 22      # favorite row (title + small subtitle)
    ROW_CUR = 18      # current row (single line)
    SEC_HEAD_H = 14
    lines: list[str] = []

    def header(y: int, label: str, src: str) -> str:
        return (
            f'<text x="24" y="{y}" font-family="ui-monospace, monospace" font-size="10" font-weight="700" fill="#00f0ff">▸ {label}</text>'
            f'<text x="{W-24}" y="{y}" font-family="ui-monospace, monospace" font-size="8" text-anchor="end" fill="#5a6275">via {src}</text>'
        )

    def fav_row(y: int, color: str, title: str, subtitle: str) -> str:
        title = escape_xml(truncate(title, 30))
        subtitle = escape_xml(truncate(subtitle, 38)) if subtitle else ""
        out = (
            f'<text x="34" y="{y}" font-family="ui-monospace, monospace" font-size="11" fill="{color}">★</text>'
            f'<text x="48" y="{y}" font-family="ui-monospace, monospace" font-size="10" fill="#e8f7ff">{title}</text>'
        )
        if subtitle:
            out += f'<text x="48" y="{y+11}" font-family="ui-monospace, monospace" font-size="8" fill="#5a6275">{subtitle}</text>'
        return out

    def cur_row(y: int, color: str, title: str, subtitle: str) -> str:
        # single-line: title — subtitle (compact)
        title = truncate(title, 26)
        if subtitle:
            text = f"{title} · {truncate(subtitle, 36 - len(title))}"
        else:
            text = title
        text = escape_xml(truncate(text, 40))
        return (
            f'<text x="34" y="{y}" font-family="ui-monospace, monospace" font-size="11" fill="{color}">▸</text>'
            f'<text x="48" y="{y}" font-family="ui-monospace, monospace" font-size="10" fill="#e8f7ff">{text}</text>'
        )

    def divider(y: int) -> str:
        return f'<line x1="24" y1="{y}" x2="{W-24}" y2="{y}" stroke="#00f0ff" stroke-opacity="0.18"/>'

    # ------------- ANIME -------------
    y = 54
    lines.append(header(y, "ANIME", anime["src"] if anime.get("current") else "json"))
    y += SEC_HEAD_H
    if anime.get("favorite"):
        lines.append(fav_row(y, "#ffb700", anime["favorite"]["title"], anime["favorite"].get("subtitle", "")))
        y += ROW_FAV
    for it in anime.get("current", []):
        lines.append(cur_row(y, "#00f0ff", it["title"], it.get("subtitle", "")))
        y += ROW_CUR

    # divider
    y += 2
    lines.append(divider(y))

    # ------------- MANGA -------------
    y += 10
    lines.append(header(y, "MANGA", manga["src"] if manga.get("current") else "json"))
    y += SEC_HEAD_H
    if manga.get("favorite"):
        lines.append(fav_row(y, "#ff79c6", manga["favorite"]["title"], manga["favorite"].get("subtitle", "")))
        y += ROW_FAV
    for it in manga.get("current", []):
        lines.append(cur_row(y, "#ff79c6", it["title"], it.get("subtitle", "")))
        y += ROW_CUR

    # footer
    foot_y = H - 8
    lines.append(
        f'<text x="24" y="{foot_y}" font-family="ui-monospace, monospace" font-size="8" fill="#5a6275">▸ now playing</text>'
        f'<text x="{W-24}" y="{foot_y}" font-family="ui-monospace, monospace" font-size="8" text-anchor="end" fill="#5a6275">'
        f'updated · {updated_at.astimezone(JST):%H:%M} {TZ_LABEL}</text>'
    )

    body = "\n  ".join(lines)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Now Playing">
  <defs>
    <linearGradient id="np-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#1a0033"/>
      <stop offset="100%" stop-color="#000814"/>
    </linearGradient>
    <pattern id="np-grid" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M20 0 H0 V20" fill="none" stroke="#00f0ff" stroke-opacity="0.05"/>
    </pattern>
    <linearGradient id="np-border" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#00f0ff"/>
      <stop offset="100%" stop-color="#ff79c6"/>
    </linearGradient>
    <style><![CDATA[
      @keyframes bracket {{ 0%, 100% {{ stroke-opacity: 0.45; }} 50% {{ stroke-opacity: 1; }} }}
      .bracket {{ animation: bracket 2.2s ease-in-out infinite; }}
    ]]></style>
  </defs>

  <rect width="{W}" height="{H}" rx="14" fill="url(#np-bg)"/>
  <rect width="{W}" height="{H}" rx="14" fill="url(#np-grid)"/>
  <rect width="{W}" height="{H}" rx="14" fill="none" stroke="url(#np-border)" stroke-width="1.4"/>

  <g class="bracket" stroke="#00f0ff" stroke-width="1.5" fill="none">
    <polyline points="14,26 14,14 26,14"/>
    <polyline points="{W-26},14 {W-14},14 {W-14},26"/>
    <polyline points="14,{H-26} 14,{H-14} 26,{H-14}"/>
    <polyline points="{W-26},{H-14} {W-14},{H-14} {W-14},{H-26}"/>
  </g>

  <text x="24"   y="36" font-family="ui-monospace, monospace" font-size="13" font-weight="700" fill="#00f0ff">▸ NOW PLAYING</text>
  <text x="{W-24}" y="36" font-family="ui-monospace, monospace" font-size="10" text-anchor="end" fill="#888">{TZ_LABEL}</text>
  <line x1="24" y1="50" x2="{W-24}" y2="50" stroke="#00f0ff" stroke-opacity="0.3"/>

  {body}
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
