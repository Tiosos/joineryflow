#!/usr/bin/env python3
"""Inline seed/fonts/*.woff2 into an artifact source file as data URIs.

The Artifact CSP blocks external font hosts, so the page must carry its own
faces. Run from the repo root:

    python3 docs/artifacts/build.py architecture-map

Writes <name>.html next to <name>.src.html.
"""
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONTS = ROOT / "seed" / "fonts"
TOKENS = {
    "__INTER_REG__": "Inter-Regular.woff2",
    "__INTER_BOLD__": "Inter-Bold.woff2",
    "__MONO_REG__": "JetBrainsMono-Regular.woff2",
    "__MONO_BOLD__": "JetBrainsMono-Bold.woff2",
}


def build(name: str) -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    html = (here / f"{name}.src.html").read_text()
    for token, filename in TOKENS.items():
        blob = base64.b64encode((FONTS / filename).read_bytes()).decode()
        html = html.replace(token, f"data:font/woff2;base64,{blob}")
    out = here / f"{name}.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "architecture-map"
    built = build(target)
    print(f"{built} — {built.stat().st_size // 1024} KB")
