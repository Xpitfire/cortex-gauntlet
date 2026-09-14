"""Generate the social-share / Open-Graph cover image for the paper (1200×630 PNG).

A clean dark card matching the paper theme — title, subtitle, authors, institution, and an accent
motif — written to `site/public/og-cover.png`. Run: `python -m tools.build_og_cover`. Re-run after a
title/author change so the link preview stays in sync.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_OUT = Path(__file__).resolve().parents[1] / "site" / "public" / "og-cover.png"
_W, _H = 1200, 630
_BG, _BG2 = (13, 15, 30), (21, 23, 43)          # dark gradient (matches the paper's --bg)
_INK, _MUTED, _ACCENT = (240, 241, 250), (150, 156, 180), (109, 94, 251)  # white / muted / purple

# macOS / Linux TrueType candidates, tried in order; fall back to PIL's bitmap font if none resolve
_FONTS = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc",
          "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def main() -> int:
    img = Image.new("RGB", (_W, _H), _BG)
    px = img.load()
    for y in range(_H):  # vertical gradient
        t = y / _H
        row = tuple(round(_BG[i] + (_BG2[i] - _BG[i]) * t) for i in range(3))
        for x in range(_W):
            px[x, y] = row
    d = ImageDraw.Draw(img, "RGBA")
    # accent glow blocks (soft, top-right) + a left rule
    d.rounded_rectangle([_W - 360, -120, _W + 120, 260], 80, fill=(_ACCENT[0], _ACCENT[1], _ACCENT[2], 38))
    d.rounded_rectangle([_W - 220, 120, _W + 120, 420], 70, fill=(_ACCENT[0], _ACCENT[1], _ACCENT[2], 26))
    d.rectangle([90, 150, 96, 470], fill=_ACCENT)  # left accent rule

    eyebrow, title = _font(26), _font(74)
    subtitle, authors, affil = _font(33), _font(27), _font(22)
    d.text((128, 150), "CORTEX  ·  TECHNICAL REPORT", font=eyebrow, fill=_ACCENT)
    d.text((126, 196), "Cortex", font=title, fill=_INK)
    d.text((128, 292), "A Fixed-Point Theory of", font=subtitle, fill=_INK)
    d.text((128, 336), "Governed Coding Agents", font=subtitle, fill=_INK)
    d.line([128, 408, 560, 408], fill=(_MUTED[0], _MUTED[1], _MUTED[2], 120), width=1)
    d.text((128, 430), "Marius-Constantin Dinu  ·  Florian Zeba", font=authors, fill=_INK)
    d.text((128, 470), "Alpha Omega Labs", font=affil, fill=_MUTED)
    d.text((128, 556), "Conditional fixed-point semantics and benchmark evidence limits.",
           font=affil, fill=_MUTED)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(_OUT, "PNG", optimize=True)
    print(f"wrote {_OUT} ({_OUT.stat().st_size // 1024} KB, {_W}×{_H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
