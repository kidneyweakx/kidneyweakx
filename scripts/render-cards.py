#!/usr/bin/env python3
"""Render the two hand-drawn profile cards.

  assets/header.svg     — Tokyo dusk banner (stars, skyline, tower, name sheen)
  assets/character.svg  — avatar card built from assets/avatar.webp

All looping motion is SMIL, so it keeps playing inside GitHub's <img>.
The status fields in character.svg are carried over, so update-status.py
can keep patching them.  Run by hand after changing the art:

    python3 scripts/render-cards.py
"""
from __future__ import annotations

import base64
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER_SVG = ROOT / "assets" / "header.svg"
CHARACTER_SVG = ROOT / "assets" / "character.svg"
AVATAR = ROOT / "assets" / "avatar.webp"

# Palette lifted from the avatar — keep in sync with scripts/update-status.py.
INK, DUSK, TRACK = "#1b1923", "#403b66", "#2a2836"
PAPER, MUTED, LILAC = "#f3ece8", "#8a86a3", "#c9c3e6"
BLUE, PINK, GOLD = "#3fb4d8", "#de5b94", "#e2b25a"
RED_EYE, GREEN_EYE = "#d0435a", "#4f9e5a"
SANS = ('ui-sans-serif, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, '
        '&quot;Hiragino Sans&quot;, &quot;Noto Sans JP&quot;, Helvetica, Arial, sans-serif')

EASE = 'calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"'
EASE_OUT = 'calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"'


def star(rnd: random.Random, x: float, y: float, r: float) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{PAPER}" opacity="{0.2 + rnd.random() * 0.5:.2f}"/>'


def motes(rnd: random.Random, n: int, x0: float, x1: float, y0: float, y1: float,
          rise: tuple[float, float], colors: list[str]) -> str:
    """Soft particles drifting upward and fading — the card's ambient motion."""
    out = []
    for _ in range(n):
        x = rnd.uniform(x0, x1)
        y = rnd.uniform(y0, y1)
        dur = rnd.uniform(7, 12)
        begin = rnd.uniform(0, 8)
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(1.1, 3):.1f}" fill="{rnd.choice(colors)}" opacity="0">'
            f'<animate attributeName="opacity" values="0;0.8;0" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0 0;{rnd.uniform(-20, 20):.1f} -{rnd.uniform(*rise):.0f}" '
            f'dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/></circle>')
    return "".join(out)


def drift(dx: float, dy: float, dur: float) -> str:
    return (f'<animateTransform attributeName="transform" type="translate" additive="sum" '
            f'values="0 0;{dx} {dy};0 0" dur="{dur}s" repeatCount="indefinite" {EASE}/>')


def flow(path: str, width: float, length: int, dur: float, begin: float = 0) -> str:
    """A bright dash running along a stripe, like current through a neon tube."""
    return (f'<path d="{path}" stroke="#ffffff" stroke-opacity="0.75" stroke-width="{width}" '
            f'stroke-dasharray="60 {length}" fill="none">'
            f'<animate attributeName="stroke-dashoffset" values="60;-{length}" dur="{dur}s" '
            f'begin="{begin}s" repeatCount="indefinite"/></path>')


def sheen_text(gid: str, x0: float, x1: float, dur: float, begin: float) -> str:
    """Gradient that slides a soft highlight across [x0, x1], then rests."""
    w = 140
    return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="0">'
            f'<stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
            f'<stop offset="0.5" stop-color="#ffffff" stop-opacity="0.95"/>'
            f'<stop offset="0.62" stop-color="{BLUE}" stop-opacity="0.6"/>'
            f'<stop offset="1" stop-color="{PINK}" stop-opacity="0"/>'
            f'<animateTransform attributeName="gradientTransform" type="translate" '
            f'values="{x0 - w} 0;{x1} 0;{x1} 0" keyTimes="0;0.3;1" dur="{dur}s" begin="{begin}s" '
            f'repeatCount="indefinite"/></linearGradient>')


# ============================================================
#  Header
# ============================================================

def skyline(rnd: random.Random) -> tuple[str, str, str]:
    """Back buildings, front buildings with blinking windows, and the tower."""
    base = 184
    back, front, windows = [], [], []

    x = 548
    while x < 900:
        w = rnd.randint(18, 38)
        h = rnd.randint(45, 100)
        back.append(f'<rect x="{x}" y="{base - h}" width="{w}" height="{h}"/>')
        if rnd.random() < 0.35:  # aviation light on the taller ones
            back.append(f'<circle cx="{x + w / 2:.1f}" cy="{base - h - 3}" r="1.6" fill="{RED_EYE}" opacity="0.8"/>')
        x += w + rnd.randint(0, 6)

    x = 566
    while x < 900:
        w = rnd.randint(22, 46)
        h = rnd.randint(26, 68)
        top = base - h
        front.append(f'<rect x="{x}" y="{top}" width="{w}" height="{h}"/>')
        for wx in range(x + 4, x + w - 4, 7):
            for wy in range(top + 6, base - 4, 9):
                if rnd.random() > 0.5:
                    continue
                color = GOLD if rnd.random() < 0.7 else LILAC
                windows.append(f'<rect x="{wx}" y="{wy}" width="3" height="4" fill="{color}" '
                               f'opacity="{0.35 + rnd.random() * 0.45:.2f}"/>')
        x += w + rnd.randint(2, 8)

    cx = 790
    tower = f"""
      <g>
        <path d="M{cx - 44} {base} L{cx - 13} 128 L{cx - 6} 92 L{cx - 2} 62 L{cx + 2} 62 L{cx + 6} 92 L{cx + 13} 128 L{cx + 44} {base} Z"
              fill="#2c2848" stroke="{PINK}" stroke-opacity="0.55" stroke-width="1.2" stroke-linejoin="round"/>
        <path d="M{cx - 30} 152 H{cx + 30} M{cx - 22} 168 H{cx + 22} M{cx - 9} 108 H{cx + 9}
                 M{cx - 30} 152 L{cx} 184 L{cx + 30} 152 M{cx - 13} 128 L{cx + 30} 152 M{cx + 13} 128 L{cx - 30} 152"
              stroke="{PINK}" stroke-opacity="0.3" stroke-width="0.8" fill="none"/>
        <rect x="{cx - 17}" y="124" width="34" height="6" rx="1" fill="{PINK}" opacity="0.8"/>
        <rect x="{cx - 8}" y="89" width="16" height="4" rx="1" fill="{PINK}" opacity="0.7"/>
        <path d="M{cx} 62 V40" stroke="{LILAC}" stroke-width="1.2"/>
        <circle cx="{cx}" cy="40" r="6" fill="{RED_EYE}" opacity="0.3"/>
        <circle cx="{cx}" cy="40" r="2.2" fill="#ff6b7d"/>
      </g>"""
    return "".join(back), tower, "".join(front) + "".join(windows)


def render_header() -> str:
    rnd = random.Random(7)
    stars = "".join(star(rnd, rnd.random() * 900, 8 + rnd.random() ** 1.4 * 120, 0.5 + rnd.random() * 1.1)
                    for _ in range(64))
    back, tower, front = skyline(rnd)
    dust = motes(rnd, 28, 0, 900, 120, 200, (60, 140), [BLUE, PINK, LILAC, GOLD])
    hem_blue, hem_pink = "M0 187.5 H900", "M0 192 H900"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 200" width="900" height="200" role="img" aria-label="kidneyweakx — software engineer in Tokyo">
  <title>kidneyweakx</title>
  <!-- generated by scripts/render-cards.py — edit the script, not this file -->
  <defs>
    <clipPath id="card"><rect width="900" height="200" rx="16"/></clipPath>
    <clipPath id="wipe">
      <rect x="36" y="60" width="0" height="90">
        <animate attributeName="width" values="0;560" dur="0.9s" begin="0.15s" fill="freeze" {EASE_OUT}/>
      </rect>
    </clipPath>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#25223f"/>
      <stop offset="0.65" stop-color="{DUSK}"/>
      <stop offset="1" stop-color="#57436f"/>
    </linearGradient>
    <radialGradient id="orb-pink"><stop offset="0" stop-color="{PINK}" stop-opacity="0.45"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>
    <radialGradient id="orb-blue"><stop offset="0" stop-color="{BLUE}" stop-opacity="0.35"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
    <linearGradient id="meteor" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="train" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{BLUE}" stop-opacity="0"/><stop offset="1" stop-color="#bdf0ff" stop-opacity="0.9"/>
    </linearGradient>
    {sheen_text("name-sheen", 40, 520, 11, 1.4)}
  </defs>

  <g clip-path="url(#card)">
    <rect width="900" height="200" fill="url(#sky)"/>

    <!-- slow glows drifting behind everything -->
    <circle cx="720" cy="190" r="190" fill="url(#orb-pink)">{drift(-40, -12, 13)}</circle>
    <circle cx="180" cy="20" r="170" fill="url(#orb-blue)">{drift(50, 18, 11)}</circle>
    <circle cx="470" cy="110" r="120" fill="url(#orb-pink)" opacity="0.5">{drift(30, -20, 17)}</circle>

    <g>{stars}</g>

    <!-- shooting star, once every 14s -->
    <g opacity="0">
      <animate attributeName="opacity" values="0;1;0;0" keyTimes="0;0.02;0.065;1" dur="14s" begin="2s" repeatCount="indefinite"/>
      <animateTransform attributeName="transform" type="translate" values="0 0;-190 76;-190 76" keyTimes="0;0.065;1" dur="14s" begin="2s" repeatCount="indefinite"/>
      <path d="M700 30 L780 -2" stroke="url(#meteor)" stroke-width="1.6" stroke-linecap="round"/>
    </g>

    <g fill="#332e57">{back}</g>
    {tower}
    <g fill="#221f37">{front}</g>
    <g>{dust}</g>

    <!-- hoodie hem with the sleeve stripes -->
    <rect y="184" width="900" height="16" fill="{INK}"/>
    <path d="{hem_blue}" stroke="{BLUE}" stroke-width="3"/>
    <path d="{hem_pink}" stroke="{PINK}" stroke-width="2"/>
    {flow(hem_blue, 3, 900, 9)}
    {flow(hem_pink, 2, 900, 9, 4.5)}
    <!-- a late train crossing the bay -->
    <rect x="-120" y="180" width="90" height="2.5" rx="1.2" fill="url(#train)">
      <animateTransform attributeName="transform" type="translate" values="0 0;1140 0;1140 0" keyTimes="0;0.55;1" dur="12s" begin="3s" repeatCount="indefinite"/>
    </rect>
  </g>

  <g font-family="{SANS}">
    <g opacity="0">
      <animate attributeName="opacity" values="0;1" dur="0.7s" begin="0.7s" fill="freeze"/>
      <ellipse cx="47" cy="47" rx="4" ry="4" fill="{RED_EYE}">
        <animate attributeName="ry" values="4;4;0.4;4;4" keyTimes="0;0.9;0.93;0.96;1" dur="6s" begin="2s" repeatCount="indefinite"/>
      </ellipse>
      <ellipse cx="61" cy="47" rx="4" ry="4" fill="{GREEN_EYE}">
        <animate attributeName="ry" values="4;4;0.4;4;4" keyTimes="0;0.9;0.93;0.96;1" dur="6s" begin="2s" repeatCount="indefinite"/>
      </ellipse>
      <text x="76" y="52" font-size="13" letter-spacing="2" fill="{LILAC}">東京 · JST+9</text>
    </g>

    <g clip-path="url(#wipe)">
      <text x="40" y="128" font-size="70" font-weight="800" letter-spacing="-2" fill="{PAPER}">kidneyweakx</text>
      <text x="40" y="128" font-size="70" font-weight="800" letter-spacing="-2" fill="url(#name-sheen)">kidneyweakx</text>
    </g>

    <text x="42" y="162" font-size="16" letter-spacing=".5" fill="{LILAC}" opacity="0">
      <animate attributeName="opacity" values="0;1" dur="0.7s" begin="0.85s" fill="freeze"/>software engineer — fullstack · iOS / Android · web3</text>
  </g>
</svg>
"""


# ============================================================
#  Character card
# ============================================================

def current_status() -> tuple[str, str, str]:
    """(dot color, status text, push line) from the card on disk, so a re-render keeps them."""
    svg = CHARACTER_SVG.read_text(encoding="utf-8") if CHARACTER_SVG.exists() else ""
    dot = re.search(r'<circle id="status-dot"[^/>]*fill="([^"]*)"', svg)
    text = re.search(r'<text id="status-text"[^>]*>([^<]*)</text>', svg)
    push = re.search(r'<text id="status-push"[^>]*>([^<]*)</text>', svg)
    return (dot.group(1) if dot else MUTED,
            text.group(1) if text else "AFK",
            push.group(1) if push else "no recent push")


def render_character() -> str:
    rnd = random.Random(11)
    color, status, push = current_status()
    avatar = base64.b64encode(AVATAR.read_bytes()).decode()

    # bokeh rising over the hoodie
    bokeh = motes(rnd, 22, 20, 340, 280, 360, (100, 220), [BLUE, PINK, LILAC, BLUE, PINK])
    stripe_blue, stripe_pink = "M12 360 H348", "M12 365 H348"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 422" width="360" height="422" role="img" aria-label="kidneyweakx avatar">
  <title>kidneyweakx</title>
  <!-- generated by scripts/render-cards.py; status fields patched by scripts/update-status.py -->
  <defs>
    <clipPath id="frame"><rect x="12" y="12" width="336" height="336" rx="14"/></clipPath>
    <linearGradient id="ring" gradientUnits="userSpaceOnUse" x1="12" y1="12" x2="348" y2="348">
      <stop offset="0" stop-color="{BLUE}"/>
      <stop offset="0.5" stop-color="{PINK}" stop-opacity="0.2"/>
      <stop offset="1" stop-color="{PINK}"/>
      <animateTransform attributeName="gradientTransform" type="rotate" values="0 180 180;360 180 180" dur="10s" repeatCount="indefinite"/>
    </linearGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.16"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    {sheen_text("name-sheen", 24, 140, 11, 1.2)}
  </defs>

  <g opacity="0">
    <animate attributeName="opacity" values="0;1" dur="0.6s" fill="freeze"/>
    <rect width="360" height="422" rx="20" fill="{INK}"/>

    <rect x="12" y="12" width="336" height="336" rx="14" fill="{DUSK}"/>
    <g clip-path="url(#frame)">
      <!-- slow breathing around her elbows -->
      <g transform="translate(180 330)"><g>
        <animateTransform attributeName="transform" type="scale" values="1;1.022;1" dur="6s" repeatCount="indefinite" {EASE}/>
        <image href="data:image/webp;base64,{avatar}" x="-168" y="-318" width="336" height="336" preserveAspectRatio="xMidYMid slice"/>
      </g></g>
      <g>{bokeh}</g>
      <!-- glass sheen sweeping the frame -->
      <rect x="-200" y="-60" width="120" height="480" fill="url(#glass)" transform="rotate(20 180 180)">
        <animateTransform attributeName="transform" type="translate" additive="sum" values="0 0;620 0;620 0" keyTimes="0;0.2;1" dur="12s" begin="1.5s" repeatCount="indefinite"/>
      </rect>
    </g>
    <rect x="12" y="12" width="336" height="336" rx="14" fill="none" stroke="url(#ring)" stroke-width="2"/>

    <path d="{stripe_blue}" stroke="{BLUE}" stroke-width="3"/>
    <path d="{stripe_pink}" stroke="{PINK}" stroke-width="2"/>
    {flow(stripe_blue, 3, 340, 6)}
    {flow(stripe_pink, 2, 340, 6, 3)}

    <g font-family="{SANS}">
      <text x="24" y="390" font-size="15" font-weight="700" fill="{PAPER}">kidneyweakx</text>
      <text x="24" y="390" font-size="15" font-weight="700" fill="url(#name-sheen)">kidneyweakx</text>
      <circle id="status-dot" cx="262" cy="385" r="4" fill="{color}"/>
      <text id="status-text" x="272" y="390" font-size="12" font-weight="600" letter-spacing="1" fill="{color}">{status}</text>
      <text id="status-push" x="24" y="408" font-size="10" fill="{MUTED}">{push}</text>
    </g>
  </g>
</svg>
"""


def main() -> int:
    HEADER_SVG.write_text(render_header(), encoding="utf-8")
    CHARACTER_SVG.write_text(render_character(), encoding="utf-8")
    print(f"wrote {HEADER_SVG.name}, {CHARACTER_SVG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
