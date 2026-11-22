"""Add UAE brand logos to Phishpedia's reference list inside the sandbox VM.

Run it with Phishpedia's own Python, as the user that owns /srv/scamshield/Phishpedia:

    sudo -u "$USER" env HOME=/srv/scamshield/home \
        /srv/scamshield/Phishpedia/.pixi/envs/default/bin/python \
        /srv/scamshield/app/brands/install_brands.py --logos /srv/scamshield/brands/logos
    sudo systemctl restart mirsad-sandbox

What it does:
1. Reads uae_brands.json (brand name -> official domains, generated from mirsad/features/brands.py).
2. For every folder logos/<Brand name>/ that holds PNG or JPEG logos, copies them to
   Phishpedia/models/expand_targetlist/<Brand name>/ (transparent pixels are flattened onto white,
   because Phishpedia converts logos to RGB and transparency would otherwise turn black).
3. Adds or extends domain_map.pkl[<Brand name>] with the brand's official domains. Phishpedia looks up
   every matched folder in this map, so a folder without an entry would break matching for all pages.
4. Deletes the cached embeddings (LOGO_FEATS.npy, LOGO_FILES.npy) and rebuilds them.

It never downloads anything. Logos are fetched by the team from each brand's own official website and
stay out of git (see README.md in this folder).
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import subprocess
import sys
import time

IMAGE_EXT = (".png", ".jpg", ".jpeg")
SKIP_PREFIXES = ("homepage", "loginpage")  # Phishpedia ignores files with these prefixes


def load_mapping(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {b["name"]: [d.lower() for d in b["domains"]] for b in data["brands"]}


def flatten_copy(src, dst):
    """Copy one logo as an RGB PNG on a white background; fall back to a plain copy without Pillow."""
    try:
        from PIL import Image
    except ImportError:
        shutil.copy2(src, dst)
        return
    with Image.open(src) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            out = bg
        else:
            out = im.convert("RGB")
        out.save(dst, format="PNG")


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--phishpedia", default=os.environ.get("PHISHPEDIA_DIR", "/srv/scamshield/Phishpedia"))
    ap.add_argument("--logos", default="/srv/scamshield/brands/logos")
    ap.add_argument("--map", default=os.path.join(here, "uae_brands.json"))
    ap.add_argument("--dry-run", action="store_true", help="report what would change and stop")
    ap.add_argument("--no-rebuild", action="store_true", help="do not rebuild the embedding cache now")
    args = ap.parse_args(argv)

    mapping = load_mapping(args.map)
    target_root = os.path.join(args.phishpedia, "models", "expand_targetlist")
    domain_map_path = os.path.join(args.phishpedia, "models", "domain_map.pkl")
    for p in (target_root, domain_map_path, args.logos):
        if not os.path.exists(p):
            sys.exit(f"Not found: {p}")

    with open(domain_map_path, "rb") as fh:
        domain_map = pickle.load(fh)
    upstream = {name.lower(): name for name in os.listdir(target_root) if not name.startswith(".")}

    plan = []
    for folder in sorted(os.listdir(args.logos)):
        src_dir = os.path.join(args.logos, folder)
        if not os.path.isdir(src_dir) or folder.startswith("."):
            continue
        if folder not in mapping:
            sys.exit(f"Folder '{folder}' is not a brand name in {os.path.basename(args.map)}. "
                     f"Use one of: {', '.join(sorted(mapping))}")
        images = [f for f in sorted(os.listdir(src_dir))
                  if f.lower().endswith(IMAGE_EXT) and not f.lower().startswith(SKIP_PREFIXES)]
        if not images:
            print(f"skip  {folder}: no PNG or JPEG logos")
            continue
        if not os.path.exists(os.path.join(src_dir, "SOURCE.txt")):
            print(f"note  {folder}: no SOURCE.txt (record the official page URL and the date fetched)")
        first = folder.lower().split(" ")[0]
        similar = [v for k, v in upstream.items() if k != folder.lower() and
                   ((len(first) >= 4 and first in k) or (len(k) >= 4 and k in folder.lower()))]
        if similar:
            print(f"note  {folder}: Phishpedia already has similar folders {similar}; check for duplicates")
        plan.append((folder, src_dir, images))

    if not plan:
        print("No logos to install.")
        return 0
    for folder, _src, images in plan:
        old = list(domain_map.get(folder, []))
        new = sorted(set(old) | set(mapping[folder]))
        print(f"add   {folder}: {len(images)} logo(s); domains {new}")
    if args.dry_run:
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    original = domain_map_path + ".orig"
    if not os.path.exists(original):
        shutil.copy2(domain_map_path, original)
    shutil.copy2(domain_map_path, f"{domain_map_path}.{stamp}.bak")

    for folder, src_dir, images in plan:
        dst_dir = os.path.join(target_root, folder)
        os.makedirs(dst_dir, exist_ok=True)
        for name in images:
            base = os.path.splitext(name)[0]
            flatten_copy(os.path.join(src_dir, name), os.path.join(dst_dir, f"mirsad_{base}.png"))
        domain_map[folder] = sorted(set(domain_map.get(folder, [])) | set(mapping[folder]))

    tmp = domain_map_path + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(domain_map, fh)
    os.replace(tmp, domain_map_path)
    for cache in ("LOGO_FEATS.npy", "LOGO_FILES.npy"):
        try:
            os.remove(os.path.join(args.phishpedia, cache))
        except FileNotFoundError:
            pass
    print(f"domain_map.pkl updated ({len(domain_map)} brands); backup {domain_map_path}.{stamp}.bak")

    if args.no_rebuild:
        print("Embedding cache deleted; it is rebuilt when the service next starts (several minutes).")
        return 0
    worker = os.path.join(os.path.dirname(here), "phishpedia_worker.py")
    print("Rebuilding the reference embeddings (several minutes on CPU) ...", flush=True)
    env = dict(os.environ, PHISHPEDIA_DIR=args.phishpedia, KMP_DUPLICATE_LIB_OK="TRUE")
    rc = subprocess.call([sys.executable, worker, "--build-cache"], cwd=args.phishpedia, env=env)
    if rc != 0:
        print("Cache rebuild failed; see the messages above. The original map is in domain_map.pkl.orig.")
        return rc
    print("Done. Now run: sudo systemctl restart mirsad-sandbox")
    return 0


if __name__ == "__main__":
    sys.exit(main())
