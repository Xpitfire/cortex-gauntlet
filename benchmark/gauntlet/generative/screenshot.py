"""Render a mock app screenshot (SVG) showing which features a harness delivered.

A synthetic-but-visual artifact for the side-by-side comparison: a browser frame with one card
per feature, green when the feature passed its e2e check, grey when it was dropped. Real
Playwright screenshots of the running app are the drop-in upgrade.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from .models import AppBrief, GenerativeResult

_COLS = 3
_CARD_W = 200
_CARD_H = 44
_PAD = 14


def render(brief: AppBrief, result: GenerativeResult, assets_dir: Path) -> str:
    features = result.rep_features
    rows = (len(features) + _COLS - 1) // _COLS
    width = _COLS * _CARD_W + _PAD
    height = 86 + rows * (_CARD_H + _PAD)
    passed = sum(f.passed for f in features)

    cards = []
    for idx, feature in enumerate(features):
        cx = _PAD + (idx % _COLS) * _CARD_W
        cy = 72 + (idx // _COLS) * (_CARD_H + _PAD)
        fill = "#1f7a44" if feature.passed else "#33384a"
        mark = "✓" if feature.passed else "·"
        cards.append(
            f'<rect x="{cx}" y="{cy}" width="{_CARD_W - _PAD}" height="{_CARD_H}" rx="8" fill="{fill}"/>'
            f'<text x="{cx + 11}" y="{cy + 27}" fill="#e6e7ee" '
            f'font-family="-apple-system,sans-serif" font-size="12">{mark} {escape(feature.name)[:22]}</text>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="#0f1222"/>'
        '<rect x="0" y="0" width="100%" height="46" fill="#22263a"/>'
        '<circle cx="20" cy="23" r="5" fill="#e5484d"/>'
        '<circle cx="38" cy="23" r="5" fill="#d9a441"/>'
        '<circle cx="56" cy="23" r="5" fill="#3fb950"/>'
        f'<text x="78" y="28" fill="#9aa0b4" font-family="monospace" font-size="13">'
        f"{escape(brief.title)} — {escape(result.harness_id)} · {passed}/{len(features)} features</text>"
        f'{"".join(cards)}</svg>'
    )
    path = assets_dir / f"{brief.id}-{result.harness_id}.svg"
    path.write_text(svg, encoding="utf-8")
    return f"assets/{path.name}"
