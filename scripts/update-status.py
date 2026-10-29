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

import base64
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

# kidneyweakx.com palette — keep in sync with scripts/render-cards.py.
INK    = "#0f0f10"
TRACK  = "#26282a"
PAPER  = "#f4e8d7"
MUTED  = "#8f877c"
CYAN   = "#3cc8f0"
PINK   = "#fc327a"
YELLOW = "#f5d63d"
SANS   = "ui-sans-serif, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, &quot;Hiragino Sans&quot;, &quot;Noto Sans JP&quot;, Helvetica, Arial, sans-serif"
HEAD   = "'Dela Gothic One', 'Hiragino Sans', sans-serif"
PIXEL  = "'DotGothic16', ui-monospace, monospace"
FONTS  = ROOT / "assets" / "fonts"

ONLINE = ("ONLINE", "#7fd8a0")
IDLE   = ("IDLE",   YELLOW)
AFK    = ("AFK",    MUTED)

BUCKETS = [
    ("MORNING", "06-12", "morning", YELLOW),
    ("DAYTIME", "12-18", "daytime", CYAN),
    ("EVENING", "18-24", "evening", PINK),
    ("NIGHT",   "00-06", "night",   PAPER),
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


SHADOW = 6
# (x, r, color, dur, begin, drift) — slow particles rising through the card
MOTES = [
    (40, 1.6, CYAN, 9, 0, 12), (96, 2.2, PINK, 11, 3, -10), (150, 1.3, PAPER, 8, 5.5, 8),
    (212, 1.8, CYAN, 10, 1.5, -14), (268, 2.4, PINK, 12, 6, 10), (318, 1.4, PAPER, 9, 2.5, -8),
]


def card_frame(w: int, h: int, uid: str) -> tuple[str, str]:
    """(defs, body): embedded fonts, a flat ink card with a paper rule and a hard
    pink offset shadow, and a few particles rising through it.
    SMIL rather than CSS so it keeps looping inside GitHub's <img>."""
    fonts = "".join(
        f"@font-face {{ font-family: '{name}'; src: url(data:font/woff2;base64,"
        f"{base64.b64encode((FONTS / file).read_bytes()).decode()}) format('woff2'); }}"
        for name, file in [("Dela Gothic One", "dela-gothic-one-latin.woff2"), ("DotGothic16", "dotgothic16-latin.woff2")]
    )
    cw, ch = w - SHADOW, h - SHADOW
    defs = f"""<style><![CDATA[{fonts}]]></style>
    <clipPath id="{uid}-clip"><rect x="2" y="2" width="{cw - 4}" height="{ch - 4}"/></clipPath>"""
    motes = "".join(
        f'<circle cx="{x}" cy="{ch - 6}" r="{r}" fill="{c}" opacity="0">'
        f'<animate attributeName="opacity" values="0;0.6;0" dur="{d}s" begin="{b}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;{dx} -{ch - 30}" dur="{d}s" begin="{b}s" repeatCount="indefinite"/></circle>'
        for x, r, c, d, b, dx in MOTES
    )
    body = f"""<rect x="{SHADOW}" y="{SHADOW}" width="{cw}" height="{ch}" fill="{PINK}"/>
  <rect x="1" y="1" width="{cw - 2}" height="{ch - 2}" fill="{INK}" stroke="{PAPER}" stroke-width="2"/>
  <g clip-path="url(#{uid}-clip)">{motes}</g>"""
    return defs, body


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
    BAR_X, BAR_W, BAR_H, ROW_GAP, Y0 = 128, 150, 10, 24, 58

    now_key = bucket_key(updated_at.astimezone(JST).hour)
    rows: list[str] = []
    for i, (label, rng, key, color) in enumerate(BUCKETS):
        c = counts.get(key, 0)
        pct = (c / max_c) if max_c else 0
        bar_w = max(int(BAR_W * pct), 6)
        pct_total = int(round(c / total * 100)) if total else 0
        y = Y0 + i * ROW_GAP
        grow = 0.2 + i * 0.09
        # bar grows in, then a soft highlight runs along it every 9s, staggered per row
        extra = (
            f'''
    <clipPath id="bar{i}"><rect x="{BAR_X}" y="0" width="{bar_w}" height="{BAR_H}"/></clipPath>
    <g clip-path="url(#bar{i})"><rect x="{BAR_X - 40}" y="0" width="40" height="{BAR_H}" fill="url(#shine)">
      <animateTransform attributeName="transform" type="translate" values="0 0;{bar_w + 40} 0;{bar_w + 40} 0" keyTimes="0;0.2;1" dur="9s" begin="{1.4 + i * 0.6:.1f}s" repeatCount="indefinite"/>
    </rect></g>'''
            if c else ""
        )
        now = f'\n    <rect x="12" y="2" width="6" height="6" fill="{color}"/>' if key == now_key else ""
        rows.append(
f"""  <g transform="translate(0,{y})">{now}
    <text x="24" y="10" font-family="{PIXEL}" font-size="13" fill="{PAPER}">{label}</text>
    <text x="84" y="10" font-family="{PIXEL}" font-size="11" fill="{MUTED}">{rng}</text>
    <rect x="{BAR_X}" y="0" width="{BAR_W}" height="{BAR_H}" fill="{TRACK}"/>
    <rect x="{BAR_X}" y="0" width="0" height="{BAR_H}" fill="{color}">
      <animate attributeName="width" values="0;{bar_w}" dur="0.9s" begin="{grow:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"/>
    </rect>{extra}
    <text x="{W - 26}" y="10" font-family="{PIXEL}" font-size="13" text-anchor="end" fill="{PAPER}">{c}<tspan fill="{MUTED}" font-size="11" dx="6">{pct_total}%</tspan></text>
  </g>"""
        )

    push_str = (
        f"last push {latest.astimezone(JST):%H:%M} {TZ_LABEL}"
        if latest else "no recent push"
    )

    defs, card = card_frame(W, H, "pc")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="When I commit (JST)">
  <defs>
    {defs}
    <linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.45"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>
  {card}
  <!-- clock: minute hand laps every 4s, hour hand every 48s -->
  <g transform="translate(31,31)" fill="none" stroke="{CYAN}" stroke-linecap="square">
    <circle r="8" stroke-width="2"/>
    <path d="M0 0 V-5" stroke-width="2"><animateTransform attributeName="transform" type="rotate" values="0;360" dur="4s" repeatCount="indefinite"/></path>
    <path d="M0 0 H3.5" stroke-width="2"><animateTransform attributeName="transform" type="rotate" values="0;360" dur="48s" repeatCount="indefinite"/></path>
  </g>
  <text x="46" y="37" font-family="{HEAD}" font-size="15" fill="{PAPER}">WHEN I COMMIT</text>
  <text x="{W - 26}" y="36" font-family="{PIXEL}" font-size="11" text-anchor="end" fill="{MUTED}">{TZ_LABEL} · LAST {total}</text>

""" + "\n".join(rows) + f"""

  <text x="24" y="{H - 22}" font-family="{PIXEL}" font-size="11" fill="{MUTED}">{push_str}</text>
  <text x="{W - 26}" y="{H - 22}" font-family="{PIXEL}" font-size="11" text-anchor="end" fill="{MUTED}">upd {updated_at.astimezone(JST):%m-%d %H:%M}</text>
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
            f'<text x="24" y="{y}" font-family="{PIXEL}" font-size="13" letter-spacing="2" fill="{CYAN}">{label}</text>'
            f'<text x="{W-26}" y="{y}" font-family="{PIXEL}" font-size="11" text-anchor="end" fill="{MUTED}">via {src}</text>'
        )

    order = [0]  # rows fade in one after another

    def row(y: int, color: str, mark: str, title: str, subtitle: str) -> str:
        title = escape_xml(truncate(title, 34))
        h = 25 if subtitle else 13
        begin = 0.25 + order[0] * 0.15
        order[0] += 1
        out = (
            f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.6s" begin="{begin:.2f}s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" values="0 6;0 0" dur="0.6s" begin="{begin:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"/>'
            +
            f'<rect x="24" y="{y-10}" width="3" height="{h}" fill="{color}"/>'
            f'<text x="36" y="{y}" font-size="13" font-weight="600" fill="{PAPER}">{title}'
            f'<tspan fill="{MUTED}" font-size="10" font-weight="400" dx="6">{mark}</tspan></text>'
        )
        if subtitle:
            out += f'<text x="36" y="{y+14}" font-size="10.5" fill="{MUTED}">{escape_xml(truncate(subtitle, 44))}</text>'
        return out + "</g>"

    def section(y: int, label: str, data: dict, color: str) -> int:
        lines.append(header(y, label, data["src"] if data.get("current") else "json"))
        y += 24
        if data.get("favorite"):
            fav = data["favorite"]
            lines.append(row(y, color, "fav", fav["title"], fav.get("subtitle", "")))
            y += 34
        for it in data.get("current", []):
            lines.append(row(y, CYAN, "now", it["title"], it.get("subtitle", "")))
            y += 34
        return y

    y = section(66, "ANIME", anime, PINK)
    lines.append(f'<line x1="24" y1="{y - 8}" x2="{W-24}" y2="{y - 8}" stroke="{TRACK}"/>')
    y = section(y + 12, "MANGA", manga, PINK)

    # Fixed height keeps the right column level with the avatar card;
    # grows only if both media types have a current entry.
    H = max(H_NOW, y + 4)
    body = "\n    ".join(lines)

    defs, card = card_frame(W, H, "np")
    # tiny equalizer next to the title
    eq = "".join(
        f'<rect x="{22 + i * 4.5}" width="3" fill="{c}">'
        f'<animate attributeName="height" values="{v}" dur="{d}s" repeatCount="indefinite"/>'
        f'<animate attributeName="y" values="{";".join(str(37 - int(n)) for n in v.split(";"))}" dur="{d}s" repeatCount="indefinite"/></rect>'
        for i, (v, d, c) in enumerate([
            ("4;12;6;10;4", 1.1, PINK), ("10;4;12;6;10", 0.9, CYAN),
            ("6;11;4;12;6", 1.3, PINK), ("12;6;10;4;12", 1.0, CYAN),
        ])
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Now watching and reading">
  <defs>
    {defs}
  </defs>
  {card}
  {eq}
  <text x="46" y="37" font-family="{HEAD}" font-size="15" fill="{PAPER}">NOW WATCHING</text>
  <text x="{W-26}" y="36" font-family="{PIXEL}" font-size="11" text-anchor="end" fill="{MUTED}">upd {updated_at.astimezone(JST):%H:%M} {TZ_LABEL}</text>
  <g font-family="{SANS}">
    {body}
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
