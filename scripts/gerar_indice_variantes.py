#!/usr/bin/env python3
"""Build deterministic H!P DEX lookup from the published Pokemon GO manifest."""
import json
import re
from collections import defaultdict
from pathlib import Path

def tokenize(original):
    filename = original.rsplit("/", 1)[-1]
    m = re.fullmatch(r"pm(\d+)(.*?)\.(?:s\.)?(?:icon|portrait)\.png", filename, re.I)
    if m:
        segments = re.findall(r"\.([fcg])([^.]*)", m.group(2), re.I)
        return {
            "source": "addressable",
            "codes": [{"type": kind.lower(), "value": value or None} for kind, value in segments],
        }
    m = re.fullmatch(r"pokemon_icon_(\d+)_(\d+)(.*?)\.png", filename, re.I)
    if m:
        return {"source": "legacy", "codes": [{"type": "form_number", "value": int(m.group(2))}]}
    m = re.fullmatch(r"pokemon_icon_pm(\d+)_(\d+)_(.*?)\.png", filename, re.I)
    if m:
        return {"source": "legacy_costume", "codes": [
            {"type": "form_number", "value": int(m.group(2))},
            {"type": "costume_code", "value": m.group(3).removesuffix("_shiny")},
        ]}
    return {"source": "unrecognized", "codes": []}

def build():
    manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
    entries = manifest["sprites"]
    targets = [e["output"] for e in entries]
    if len(targets) != len(set(targets)):
        raise ValueError("Manifest has duplicate destination paths; refusing to generate index")
    species = defaultdict(lambda: {"normal": None, "shiny": None, "variants": []})
    unresolved = 0
    for entry in entries:
        dex = entry["dex"]
        if not isinstance(dex, int) or dex <= 0:
            raise ValueError(f"Invalid Pokédex number: {entry}")
        path = entry["output"]
        shiny = bool(entry["shiny"])
        record = species[str(dex)]
        base_path = f"{'shiny' if shiny else 'normal'}/{dex}.webp"
        if path == base_path:
            if record["shiny" if shiny else "normal"] is not None:
                raise ValueError(f"Duplicate canonical sprite: {base_path}")
            record["shiny" if shiny else "normal"] = path
            continue
        parsed = tokenize(entry["original"])
        codes = parsed["codes"]
        ambiguous = parsed["source"] != "addressable" or any(x["value"] is None for x in codes)
        if ambiguous:
            unresolved += 1
        record["variants"].append({
            "path": path,
            "shiny": shiny,
            "category": entry["category"],
            "original": entry["original"],
            "source_family": entry["source_family"],
            "codes": codes,
            "needs_form_review": ambiguous,
        })
    result = {
        "schema_version": 1,
        "description": "Exact filename lookup. No inferred equivalence between historical form codes.",
        "source_manifest": "manifest.json",
        "totals": {
            "sprites": len(entries),
            "species": len(species),
            "canonical": len(entries) - sum(len(x["variants"]) for x in species.values()),
            "variant_records": sum(len(x["variants"]) for x in species.values()),
            "variants_needing_review": unresolved,
        },
        "by_dex": dict(sorted(species.items(), key=lambda kv: int(kv[0]))),
    }
    Path("indice-variantes.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["totals"], indent=2))
if __name__ == "__main__":
    build()
