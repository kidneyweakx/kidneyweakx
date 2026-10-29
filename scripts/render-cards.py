#!/usr/bin/env python3
"""Render the two hand-drawn profile cards in the kidneyweakx.com look.

  assets/header.svg     — the rooftop stage: sky + city plates in parallax,
                          a light band across the city, sparkles on twos
  assets/character.svg  — avatar card built from assets/avatar.webp

Plates come from the blog's stage (cropped into assets/stage/), fonts are
Dela Gothic One + DotGothic16 (OFL, assets/fonts/), embedded so they render
inside GitHub's <img>. Looping motion is SMIL for the same reason.
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
ASSETS = ROOT / "assets"
HEADER_SVG = ASSETS / "header.svg"
CHARACTER_SVG = ASSETS / "character.svg"

# kidneyweakx.com palette — keep in sync with scripts/update-status.py.
INK, PAPER, MUTED = "#0f0f10", "#f4e8d7", "#8f877c"
PINK, CYAN, YELLOW = "#fc327a", "#3cc8f0", "#f5d63d"
HEAD = "'Dela Gothic One', 'Hiragino Sans', sans-serif"
PIXEL = "'DotGothic16', ui-monospace, monospace"

EASE = 'calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"'
EASE_OUT = 'calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"'


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def font_css() -> str:
    return "".join(
        f"@font-face {{ font-family: '{name}'; src: url(data:font/woff2;base64,{b64(ASSETS / 'fonts' / file)}) format('woff2'); }}"
        for name, file in [("Dela Gothic One", "dela-gothic-one-latin.woff2"), ("DotGothic16", "dotgothic16-latin.woff2")]
    )


def frame(w: int, h: int, shadow: int) -> str:
    """Flat ink card, paper rule, hard pink offset shadow — no radii."""
    return (f'<rect x="{shadow}" y="{shadow}" width="{w - shadow}" height="{h - shadow}" fill="{PINK}"/>'
            f'<rect x="1" y="1" width="{w - shadow - 2}" height="{h - shadow - 2}" fill="{INK}" stroke="{PAPER}" stroke-width="2"/>')


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


def flow(path: str, width: float, length: int, dur: float, begin: float = 0, opacity: float = 0.75) -> str:
    """A bright dash running along a stripe, like current through a neon tube."""
    return (f'<path d="{path}" stroke="#ffffff" stroke-opacity="{opacity}" stroke-width="{width}" '
            f'stroke-dasharray="60 {length}" fill="none">'
            f'<animate attributeName="stroke-dashoffset" values="60;-{length}" dur="{dur}s" '
            f'begin="{begin}s" repeatCount="indefinite"/></path>')


def sparkle(x: float, y: float, s: float, color: str, phase: float) -> str:
    """Four-point star pulsing on twos: big for two frames, mid for two, small for twelve (8 fps)."""
    d = f"M0 {-s:.1f}Q0 0 {s:.1f} 0Q0 0 0 {s:.1f}Q0 0 {-s:.1f} 0Q0 0 0 {-s:.1f}Z"
    steps = ";".join(["1.6", "1.6", "1.15", "1.15"] + ["0.75"] * 12)
    return (f'<g transform="translate({x:.1f} {y:.1f})"><path d="{d}" fill="{color}">'
            f'<animateTransform attributeName="transform" type="scale" values="{steps}" calcMode="discrete" '
            f'dur="2s" begin="{phase:.2f}s" repeatCount="indefinite"/></path></g>')


# ============================================================
#  Header
# ============================================================

def render_header() -> str:
    W, H, SH = 900, 200, 8
    cw, ch = W - SH, H - SH
    # Plates are 1672x360 crops; drawn 940 wide from x=-34 so a 26px sway never shows an edge.
    pw, px, py = 940, -34, -6
    sky_y = py + 10  # drop the sky a touch so the moon clears the top rule
    k = pw / 1672
    ph = 360 * k

    def on_sky(x: float, y: float) -> tuple[float, float]:
        return px + x * k, sky_y + (y - 30) * k  # sky crop starts at plate y=30

    # sparkles sit on the stars already painted in the sky plate
    stars = [(822, 78, CYAN), (860, 155, PAPER), (922, 268, CYAN), (1240, 60, PAPER),
             (1298, 162, CYAN), (1418, 45, CYAN), (82, 272, CYAN)]
    rnd = random.Random(3)
    sparkles = "".join(sparkle(*on_sky(x, y), 5 + rnd.random() * 3, c, rnd.random() * 2) for x, y, c in stars)
    sway = 'dur="18s" repeatCount="indefinite" ' + EASE

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="kidneyweakx — software engineer in Tokyo">
  <title>kidneyweakx</title>
  <!-- generated by scripts/render-cards.py — edit the script, not this file -->
  <defs>
    <style><![CDATA[{font_css()}]]></style>
    <clipPath id="card"><rect x="2" y="2" width="{cw - 4}" height="{ch - 4}"/></clipPath>
    <clipPath id="wipe">
      <rect x="20" y="60" width="0" height="80">
        <animate attributeName="width" values="0;620" dur="0.9s" begin="0.15s" {EASE_OUT} fill="freeze"/>
      </rect>
    </clipPath>
    <image id="far" href="data:image/webp;base64,{b64(ASSETS / 'stage' / 'far.webp')}" x="{px}" y="{py}" width="{pw}" height="{ph:.1f}"/>
    <mask id="city" mask-type="alpha" maskUnits="userSpaceOnUse" x="-100" y="-100" width="1200" height="400"><use href="#far"/></mask>
    <linearGradient id="wash" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{INK}" stop-opacity="0.92"/>
      <stop offset="0.36" stop-color="{INK}" stop-opacity="0.72"/>
      <stop offset="0.62" stop-color="{INK}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  {frame(W, H, SH)}
  <g clip-path="url(#card)">
    <!-- sky: moon, clouds, sparkles — the far depth, barely moves -->
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 0;10 -1;0 0" {sway}/>
      <image href="data:image/webp;base64,{b64(ASSETS / 'stage' / 'sky.webp')}" x="{px}" y="{sky_y}" width="{pw}" height="{ph:.1f}"/>
      {sparkles}
      <!-- a shooting star every 11s, 600ms long -->
      <path d="M0 0 L46 25" stroke="{PAPER}" stroke-width="2" stroke-linecap="round" opacity="0">
        <animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.005;0.045;0.055;1" dur="11s" begin="3s" repeatCount="indefinite"/>
        <animateTransform attributeName="transform" type="translate" values="300 6;400 60;400 60" keyTimes="0;0.055;1" dur="11s" begin="3s" repeatCount="indefinite"/>
      </path>
    </g>
    <!-- city: the near depth, sways more; a light band crosses it now and then -->
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 0;26 -3;0 0" {sway}/>
      <use href="#far"/>
      <g mask="url(#city)">
        <path d="M0 0 H70 L-100 {H} H-170 Z" fill="{PAPER}" fill-opacity="0.22">
          <animateTransform attributeName="transform" type="translate" values="-60 0;1160 0;1160 0" keyTimes="0;0.16;1" dur="9s" begin="1.5s" repeatCount="indefinite"/>
        </path>
      </g>
    </g>
    <rect width="{W}" height="{H}" fill="url(#wash)"/>
  </g>

  <g opacity="0">
    <animate attributeName="opacity" values="0;1" dur="0.5s" begin="0.6s" fill="freeze"/>
    <text x="34" y="52" font-family="{PIXEL}" font-size="14" letter-spacing="3" fill="{CYAN}">PLAYER 01 · TOKYO JST+9</text>
  </g>
  <g clip-path="url(#wipe)" font-family="{HEAD}" font-size="58" letter-spacing="1">
    <text x="36" y="120" fill="{PINK}">kidneyweakx</text>
    <text x="32" y="116" fill="{PAPER}">kidneyweakx</text>
  </g>
  <g opacity="0">
    <animate attributeName="opacity" values="0;1" dur="0.5s" begin="0.85s" fill="freeze"/>
    <rect x="32" y="136" width="10" height="10" fill="{YELLOW}"/>
    <text x="50" y="146" font-family="{PIXEL}" font-size="15" letter-spacing="1.5" fill="{PAPER}">SOFTWARE ENGINEER — FULLSTACK / MOBILE / WEB3</text>
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
    W, H, SH = 360, 422, 6
    rnd = random.Random(11)
    color, status, push = current_status()
    # bokeh rising over the hoodie
    bokeh = motes(rnd, 22, 20, 330, 270, 340, (100, 220), [CYAN, PINK, PAPER, CYAN, PINK])
    pic = 324  # portrait square, inset 14
    stripe_cyan, stripe_pink = f"M14 {14 + pic + 10} H{14 + pic}", f"M14 {14 + pic + 15} H{14 + pic}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="kidneyweakx avatar">
  <title>kidneyweakx</title>
  <!-- generated by scripts/render-cards.py; status fields patched by scripts/update-status.py -->
  <defs>
    <style><![CDATA[{font_css()}]]></style>
    <clipPath id="photo"><rect x="14" y="14" width="{pic}" height="{pic}"/></clipPath>
    <linearGradient id="glass" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.14"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <g opacity="0">
    <animate attributeName="opacity" values="0;1" dur="0.6s" fill="freeze"/>
    {frame(W, H, SH)}

    <g clip-path="url(#photo)">
      <rect x="14" y="14" width="{pic}" height="{pic}" fill="#403b66"/>
      <!-- slow breathing around her elbows -->
      <g transform="translate(176 320)"><g>
        <animateTransform attributeName="transform" type="scale" values="1;1.022;1" dur="6s" repeatCount="indefinite" {EASE}/>
        <image href="data:image/webp;base64,{b64(ASSETS / 'avatar.webp')}" x="-162" y="-306" width="{pic}" height="{pic}" preserveAspectRatio="xMidYMid slice"/>
      </g></g>
      <g>{bokeh}</g>
      <!-- glass sheen sweeping the frame -->
      <rect x="-200" y="-60" width="120" height="480" fill="url(#glass)" transform="rotate(20 176 176)">
        <animateTransform attributeName="transform" type="translate" additive="sum" values="0 0;620 0;620 0" keyTimes="0;0.2;1" dur="12s" begin="1.5s" repeatCount="indefinite"/>
      </rect>
    </g>
    <rect x="14" y="14" width="{pic}" height="{pic}" fill="none" stroke="{PAPER}" stroke-width="2"/>

    <path d="{stripe_cyan}" stroke="{CYAN}" stroke-width="3"/>
    <path d="{stripe_pink}" stroke="{PINK}" stroke-width="2"/>
    {flow(stripe_cyan, 3, 330, 6)}
    {flow(stripe_pink, 2, 330, 6, 3)}

    <text x="16" y="386" font-family="{HEAD}" font-size="18" fill="{PAPER}">kidneyweakx</text>
    <circle id="status-dot" cx="262" cy="380" r="4" fill="{color}"/>
    <text id="status-text" x="272" y="385" font-family="{PIXEL}" font-size="13" letter-spacing="1" fill="{color}">{status}</text>
    <text id="status-push" x="16" y="404" font-family="{PIXEL}" font-size="11" fill="{MUTED}">{push}</text>
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
