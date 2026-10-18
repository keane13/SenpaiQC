"""Copy a few validation images into data/samples for the in-app gallery.

  python data/make_samples.py [--n 4]
Uses data/splits/classify/val (created by prepare_casting.py), never the golden set.
"""
import argparse
import json
import random
import shutil
from pathlib import Path

HERE = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=4, help="images per class")
a = ap.parse_args()
val = HERE / "splits" / "classify" / "val"
if not val.exists():
    raise SystemExit("run data/prepare_casting.py first")
out = HERE / "samples"
out.mkdir(exist_ok=True)
meta, rng = {}, random.Random(3)
for cls in ("ok", "defective"):
    files = sorted((val / cls).glob("*.jp*g"))
    for p in rng.sample(files, min(a.n, len(files))):
        name = f"{cls}-{p.stem}.jpg"
        shutil.copy2(p, out / name)
        meta[name] = {"label": cls, "source": "Kaggle casting dataset (validation split)"}
(out / "samples.json").write_text(json.dumps(meta, indent=1))
print(f"wrote {len(meta)} samples to {out}")
