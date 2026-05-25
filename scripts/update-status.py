#!/usr/bin/env python3
"""Refresh commit-activity status assets.

Two outputs, both written from the same GitHub events fetch:

  1. assets/character.svg   — three small fields patched in place
       <circle id="status-dot">    breathing-dot color
       <text   id="status-push">   "last push · HH:MM UTC · Nh ago"
       <text   id="status-text">   ONLINE / IDLE / AFK (color matches dot)

  2. assets/productive.svg  — full cyberpunk bar chart of recent
     commit activity by UTC bucket (morning / daytime / evening / night).
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
CHARACTER_SVG  = ROOT / "assets" / "character.svg"
PRODUCTIVE_SVG = ROOT / "assets" / "productive.svg"

# All displayed clock times use JST (UTC+9), matching kidneyweakx's timezone.
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


def bucket_key(h: int) -> str:
    if   6 <= h < 12:  return "morning"
    elif 12 <= h < 18: return "daytime"
    elif 18 <= h < 24: return "evening"
    else:              return "night"


def fetch_events(user: str) -> list[dict]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{user}-status-updater",
    }
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
        print(f"fetch failed: {exc}", file=sys.stderr)
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
"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 230" width="600" height="230" role="img" aria-label="Productive Time UTC">
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
      @keyframes pulse { 0%, 100% { opacity: 0.85; } 50% { opacity: 1; } }
      .live { animation: pulse 2.4s ease-in-out infinite; }
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


def main() -> int:
    events = fetch_events(USER)
    latest = find_latest_push(events)
    counts = aggregate_buckets(events)
    (status, color), push_str = classify(latest)

    changed_char = patch_character(status, color, push_str)

    new_prod = render_productive_svg(counts, latest, dt.datetime.now(dt.timezone.utc))
    existing = PRODUCTIVE_SVG.read_text(encoding="utf-8") if PRODUCTIVE_SVG.exists() else ""
    changed_prod = new_prod != existing
    if changed_prod:
        PRODUCTIVE_SVG.write_text(new_prod, encoding="utf-8")

    print(f"status:  {status} · {push_str}")
    print(f"buckets: {counts}")
    print(f"character.svg changed: {changed_char}")
    print(f"productive.svg changed: {changed_prod}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
