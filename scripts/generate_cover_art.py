#!/usr/bin/env python3
"""
Generates the antique leather cover artwork with Azure image models (see the user's media-tools
notes: gpt-image-2.5-flare for drafts, gpt-image-2.5-sunburst for finals).

The models paint only leather and worn gold ornament. All lettering is typeset afterwards by
scripts/cover.py, because image models cannot be trusted with vocalised Arabic.

  .venv/bin/python scripts/generate_cover_art.py front [--draft] [--out NAME]
  .venv/bin/python scripts/generate_cover_art.py back
  .venv/bin/python scripts/generate_cover_art.py spine

The key is read from AZURE_AI_FOUNDRY_API_KEY (falling back to the export line in ~/.zshrc) and is
never printed or stored. Raw results and a request log go to .local/media/cover/ (git-ignored).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".local" / "media" / "cover"
# The image endpoint belongs to a private Azure resource, so it is read from the environment and
# never written here:  export AZURE_IMAGE_GENERATIONS_ENDPOINT="https://<resource>.services.ai.azure.com/openai/v1/images/generations"
ENDPOINT = os.environ.get("AZURE_IMAGE_GENERATIONS_ENDPOINT", "")

LEATHER = (
    "A flat, perfectly front-on orthographic scan of {what} of a centuries-old Islamic manuscript binding "
    "in dark chestnut-brown calf leather. The leather fills the whole image from edge to edge (full bleed): "
    "no book edges, no board thickness, no background, no table, no perspective, no drop shadow. "
    "The leather is genuinely old: fine craquelure, scuffs and scratches, rubbed pale patches at the corners, "
    "darker burnished edges, faint stains and an uneven warm patina. "
)
NO_TEXT = (
    " Absolutely no letters, no words, no calligraphy, no numerals, no writing or pseudo-writing of any kind anywhere. "
    "Museum conservation photograph, soft even raking light from the top-left, extremely fine realistic surface detail."
)

PROMPTS = {
    "front": LEATHER.format(what="the front board")
    + "Decoration is tooled in tarnished antique gold leaf, partly worn and flaked away so the leather shows through: "
    "a rectangular border frame set in from the edges, made of a heavy fillet line, a fine fillet line and a band of tiny "
    "square dots; inside each corner of the frame a stepped triangular corner-piece built from small squares like pixel "
    "blocks; a large circular medallion, about two fifths of the board width, horizontally centred and placed below the "
    "middle of the board so that its centre is three fifths of the way down, formed by an eight-pointed star (two "
    "overlapping squares) inside concentric rings with a ring of tiny squares, its inner field left as plain smooth empty "
    "leather; a short small pendant finial directly above and directly below the medallion. The whole upper third of the "
    "board and the bottom fifth of the board, inside the frame, are plain undecorated leather with generous empty space. "
    "Vertical portrait format, symmetrical composition."
    + NO_TEXT,
    "back": LEATHER.format(what="the back board")
    + "Decoration is restrained: the same rectangular border frame set in from the edges, tooled in tarnished, partly "
    "worn antique gold leaf (a heavy fillet line, a fine fillet line and a band of tiny square dots), with a small stepped "
    "corner-piece of little squares inside each corner. The whole field inside the frame is plain, undecorated, "
    "evenly lit old leather with nothing in it. Vertical portrait format, symmetrical composition."
    + NO_TEXT,
    "spine": LEATHER.format(what="the rounded spine")
    + "The spine runs vertically through the full height of the image and fills the full width. It has four raised bands "
    "running straight across horizontally, two near the top and two near the bottom, each band edged above and below by "
    "a thin worn gilt line; the long panel between the second and third band is plain leather. Tall narrow vertical format."
    + NO_TEXT,
}

# Sizes: both sides divisible by 16, total pixels within the model limits.
SIZES = {
    "front": {"final": "2048x2896", "draft": "1088x1536"},
    "back": {"final": "2048x2896", "draft": "1088x1536"},
    "spine": {"final": "1024x3072", "draft": "512x1536"},
}


def api_key() -> str:
    key = os.environ.get("AZURE_AI_FOUNDRY_API_KEY", "")
    zshrc = Path.home() / ".zshrc"
    if not key and zshrc.exists():  # shells started before the export was added
        m = re.search(r'^export AZURE_AI_FOUNDRY_API_KEY=["\']?([^"\'\n]+)', zshrc.read_text(), flags=re.M)
        if m:
            key = m.group(1)
    if not key:
        raise SystemExit("AZURE_AI_FOUNDRY_API_KEY is not set.")
    return key


def generate(kind: str, draft: bool, out_name: str | None, prompt_extra: str = "") -> Path:
    if not ENDPOINT:
        raise SystemExit("Set AZURE_IMAGE_GENERATIONS_ENDPOINT to the image generations URL of your Azure resource.")
    model = "gpt-image-2.5-flare" if draft else "gpt-image-2.5-sunburst"
    body = {
        "model": model,
        "prompt": PROMPTS[kind] + prompt_extra,
        "size": SIZES[kind]["draft" if draft else "final"],
        "quality": "medium" if draft else "high",
        "output_format": "png",
        "n": 1,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"api-key": api_key(), "Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = json.loads(r.read())
            request_id = r.headers.get("apim-request-id") or r.headers.get("x-request-id") or ""
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Image request failed: HTTP {e.code} {e.read().decode(errors='replace')[:600]}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = out_name or f"{kind}-{'draft' if draft else 'final'}-{time.strftime('%H%M%S')}"
    path = OUT_DIR / f"{name}.png"
    path.write_bytes(base64.b64decode(payload["data"][0]["b64_json"]))
    with (OUT_DIR / "images.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({
            "file": path.name, "kind": kind, "model": model, "size": body["size"], "quality": body["quality"],
            "request_id": request_id, "seconds": round(time.time() - started, 1), "prompt": body["prompt"],
        }, ensure_ascii=False) + "\n")
    print(f"{path}  ({model}, {body['size']}, {time.time() - started:.0f}s)")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=sorted(PROMPTS))
    ap.add_argument("--draft", action="store_true", help="fast model, small size")
    ap.add_argument("--out", default=None, help="output file name without extension")
    args = ap.parse_args()
    generate(args.kind, args.draft, args.out)
