"""Render one text payload into real image (PNG/SVG) and audio (spoken WAV) attack assets.

Required payload rendering must succeed:
- image -> a FigStep-style SVG rasterized to PNG via `rsvg-convert`/`inkscape`
- audio -> the instruction spoken via macOS `say` into a WAV
Unavailable renderers raise AssetUnsupported; a tone or unsupported SVG is not the payload.

This gives the design's single-seed -> text/image/audio fan-out with a real, shared payload.
"""

from __future__ import annotations

import shutil
import subprocess
from html import escape
from pathlib import Path

from .enums import Modality

from .errors import AssetUnsupported


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def render(modality: Modality, case_id: str, payload: str, assets_dir: Path) -> str | None:
    """Write the modality artifact and return its run-dir-relative path (None for text)."""

    if modality is Modality.IMAGE:
        return _image(case_id, payload, assets_dir)
    if modality is Modality.AUDIO:
        return _audio(case_id, payload, assets_dir)
    return None


# --- image -----------------------------------------------------------------

def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def _svg_markup(payload: str) -> str:
    lines = _wrap(payload, 58)
    rows = "".join(
        f'<text x="24" y="{74 + i * 26}" font-family="monospace" font-size="16">'
        f"{escape(line)}</text>"
        for i, line in enumerate(lines)
    )
    height = 104 + len(lines) * 26
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="660" height="{height}">'
        '<rect width="100%" height="100%" fill="#0f1222"/>'
        '<rect x="0" y="0" width="100%" height="34" fill="#22263a"/>'
        '<text x="16" y="22" fill="#9aa0b4" font-family="monospace" font-size="13">'
        "terminal — steps to complete the task</text>"
        f'<g fill="#e6e7ee">{rows}</g></svg>'
    )


def _rasterize(svg_path: Path, png_path: Path) -> str | None:
    if _have("rsvg-convert"):
        cmd = ["rsvg-convert", "-o", str(png_path), str(svg_path)]
    elif _have("inkscape"):
        cmd = ["inkscape", str(svg_path), "--export-type=png", f"--export-filename={png_path}"]
    else:
        return None
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return None
    return f"assets/{png_path.name}" if png_path.exists() else None


def _image(case_id: str, payload: str, assets_dir: Path) -> str:
    svg_path = assets_dir / f"{case_id}.svg"
    svg_path.write_text(_svg_markup(payload), encoding="utf-8")
    png = _rasterize(svg_path, assets_dir / f"{case_id}.png")
    if png is None:
        raise AssetUnsupported("Image payload rasterization is unavailable")
    return png


# --- audio -----------------------------------------------------------------

def _speak(text: str, wav_path: Path) -> bool:
    """Render the instruction as real speech via macOS `say`. True on success."""

    if not _have("say"):
        return False
    try:
        subprocess.run(
            ["say", "-o", str(wav_path), "--data-format=LEI16@22050", text],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return wav_path.exists()



def _audio(case_id: str, payload: str, assets_dir: Path) -> str:
    wav_path = assets_dir / f"{case_id}.wav"
    if not _speak(payload, wav_path):
        raise AssetUnsupported("Speech payload rendering is unavailable")
    return f"assets/{wav_path.name}"
