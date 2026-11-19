#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from PIL import Image, ImageChops

LEGACY = re.compile(r"pokemon_icon_(\d+)_(\d+)(.*?)\.png$", re.I)
NEW = re.compile(r"pm(\d+)(.*?)\.(s\.)?icon\.png$", re.I)
ALIASES = {"galarian":"galar", "alolan":"alola", "hisuian":"hisui", "paldean":"paldea", "mega_x":"mega-x", "mega_y":"mega-y"}
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def parse(p):
    m = NEW.fullmatch(p.name)
    if m:
        num, tail, shiny = m.groups()
        parts = re.findall(r"\.([a-zA-Z])([^.]*)", tail)
        label = "-".join(slug(ALIASES.get(v.lower(), v)) if k.lower()=="f" else slug(k+"-"+v) for k,v in parts)
        kind = "costumes" if any(k.lower()=="c" for k,v in parts) else "forms" if parts else "normal"
        return int(num), bool(shiny), label, kind, "addressable"
    m = LEGACY.fullmatch(p.name)
    if m:
        num, form, tail = m.groups()
        shiny = tail.lower().endswith("_shiny")
        tail = re.sub(r"_shiny$", "", tail, flags=re.I).strip("_")
        label = "" if form=="00" and not tail else slug("form-"+form+("-"+tail if tail else ""))
        return int(num), shiny, label, "forms" if label else "normal", "legacy"
    return None, False, "", "unclassified", "unknown"
def pixels(p):
    with Image.open(p) as im:
        return im.convert("RGBA").copy()
def equal(a,b):
    return a.size==b.size and ImageChops.difference(a,b).getbbox() is None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    args=ap.parse_args()
    source=args.source/"Images"/"Pokemon"
    if not source.is_dir():
        raise SystemExit("Missing source folder: "+str(source))
    files=sorted(source.rglob("*.png"), key=lambda p:(0 if "Addressable Assets" in p.parts else 1,p.as_posix().lower()))
    if not files:
        raise SystemExit("No PNG images found")
    manifest=Path("manifest.json")
    if manifest.exists():
        previous=json.loads(manifest.read_text(encoding="utf-8"))
        for rec in previous.get("sprites",[]):
            dest=Path(rec["output"])
            if dest.parts and dest.parts[0] in ("normal","shiny","forms","costumes","unclassified") and dest.suffix==".webp" and dest.is_file():
                dest.unlink()
    used={}
    records=[]
    stats=Counter()
    for src in files:
        num,shiny,label,kind,family=parse(src)
        base=str(num) if num is not None else slug(src.relative_to(source).with_suffix("").as_posix())
        if label: base+="-"+label
        folder=("shiny" if shiny else "normal") if kind in ("normal","forms") else kind
        if shiny and folder in ("costumes","unclassified"): base+="-shiny"
        rel=folder+"/"+base+".webp"
        current=pixels(src)
        alias=False
        if rel in used:
            if equal(current,used[rel]):
                alias=True
                stats["aliases"]+=1
            else:
                suffix="-legacy" if family=="legacy" else "-addressable"
                candidate=folder+"/"+base+suffix+".webp"
                if candidate in used:
                    token=hashlib.sha256(src.relative_to(source).as_posix().encode()).hexdigest()[:12]
                    candidate=folder+"/"+base+suffix+"-"+token+".webp"
                rel=candidate
                stats["collisions_preserved"]+=1
        if not alias:
            dest=Path(rel)
            dest.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(["cwebp","-quiet","-lossless","-exact","-m","6",str(src),"-o",str(dest)],check=True)
            if not equal(current,pixels(dest)):
                raise RuntimeError("Pixel/alpha mismatch: "+str(src))
            used[rel]=current
            stats["webp"]+=1
        records.append({"original":src.relative_to(source).as_posix(),"output":rel,"dex":num,
                        "shiny":shiny,"category":kind,"source_family":family,"alias_of_existing":alias})
        stats["png"]+=1
    manifest.write_text(json.dumps({"source":"https://github.com/PokeMiners/pogo_assets/tree/master/Images/Pokemon",
             "format":"WebP lossless, exact RGBA pixels and dimensions",
             "sprites":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary="PNG: {png}; WebP: {webp}; aliases: {aliases}; different collisions preserved: {collisions_preserved}".format(**{k:stats[k] for k in ("png","webp","aliases","collisions_preserved")})
    print(summary)
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("### Pokemon GO import\n\n"+summary+"\n")
if __name__=="__main__":
    main()
