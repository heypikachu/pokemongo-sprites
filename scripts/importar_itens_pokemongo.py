#!/usr/bin/env python3
"""Convert PokeMiners Images/Items into pixel-exact lossless WebP."""
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

SOURCE = Path("upstream/Images/Items")
OUTPUT = Path("items")
MANIFEST = Path("items-manifest.json")


def slug(stem):
    stem = re.sub(r"_sprite$", "", stem, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def rgba(path):
    with Image.open(path) as im:
        return im.convert("RGBA").copy()


def same_pixels(a, b):
    return a.size == b.size and ImageChops.difference(a, b).getbbox() is None


def main():
    if not SOURCE.is_dir():
        raise SystemExit("Missing source folder: " + str(SOURCE))
    files = sorted(SOURCE.rglob("*.png"), key=lambda p: p.as_posix().lower())
    if not files:
        raise SystemExit("No PNG files found in Images/Items")

    # Preserve unrelated files and remove only previously manifest-tracked outputs.
    if MANIFEST.exists():
        previous = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in previous.get("items", []):
            old = Path(entry["output"])
            if (len(old.parts) >= 2 and old.parts[0] == "items"
                    and old.suffix == ".webp" and old.is_file()):
                old.unlink()

    used = set()
    records = []
    totals = Counter()
    for src in files:
        relative = src.relative_to(SOURCE).as_posix()
        short = slug(src.stem)
        if not short:
            raise RuntimeError("Empty normalized name: " + relative)
        target = f"items/{short}.webp"
        if target in used:
            suffix = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:10]
            target = f"items/{short}-{suffix}.webp"
            totals["name_collisions"] += 1
        if target in used:
            raise RuntimeError("Destination collision: " + target)
        used.add(target)
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        original = rgba(src)
        subprocess.run(["cwebp", "-quiet", "-lossless", "-exact", "-m", "6",
                        str(src), "-o", str(dest)], check=True)
        converted = rgba(dest)
        if not same_pixels(original, converted):
            raise RuntimeError("Dimensions, RGBA or transparency changed: " + relative)
        source_bytes = src.stat().st_size
        webp_bytes = dest.stat().st_size
        totals["png_bytes"] += source_bytes
        totals["webp_bytes"] += webp_bytes
        records.append({
            "original": relative,
            "output": target,
            "width": original.width,
            "height": original.height,
            "png_bytes": source_bytes,
            "webp_bytes": webp_bytes,
            "sha256_webp": hashlib.sha256(dest.read_bytes()).hexdigest()
        })
    records.sort(key=lambda x: x["output"])
    upstream_sha = subprocess.run(["git", "-C", "upstream", "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
    document = {
        "schema_version": 1,
        "source": "https://github.com/PokeMiners/pogo_assets/tree/master/Images/Items",
        "source_commit": upstream_sha,
        "encoding": "WebP lossless -exact; RGBA pixels and dimensions verified",
        "item_count": len(records),
        "items": records,
    }
    MANIFEST.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    pct = 100 * (1 - totals["webp_bytes"] / totals["png_bytes"])
    summary = (
        f"### Pokémon GO items validation\n\n"
        f"- PNG files checked: **{len(files)}**\n"
        f"- WebP files generated: **{len(records)}**\n"
        f"- Name collisions safely resolved: **{totals['name_collisions']}**\n"
        f"- Source size: **{totals['png_bytes']/1024:.1f} KiB**\n"
        f"- Output size: **{totals['webp_bytes']/1024:.1f} KiB**\n"
        f"- Total storage change: **{pct:.1f}%** (positive is a saving)\n"
        f"- Different RGBA pixels: **0**\n"
    )
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as report:
            report.write(summary)


if __name__ == "__main__":
    main()
