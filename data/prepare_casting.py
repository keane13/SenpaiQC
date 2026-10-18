"""Split the public casting-product dataset into train / val / golden.

Dataset: "casting product image data for quality inspection" (Kaggle, ravirajsinh45),
pump impeller top views, classes def_front / ok_front. Check and record its licence in
docs/licences.md before use. Download it yourself (needs a Kaggle account):

  kaggle datasets download -d ravirajsinh45/real-life-industrial-dataset-of-casting-product -p data/raw --unzip

Then:  python data/prepare_casting.py

Output
  data/splits/classify/{train,val}/{ok,defective}/...   for Ultralytics classification training
  data/golden/{ok,defective}/... + manifest.csv          held out, never trained on
  data/colab/senpaiqc_data.zip                         both, for eval/train_yolo_colab.ipynb
The golden set is drawn from the dataset's own test split so it never overlaps training.
"""
from __future__ import annotations

import csv
import random
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
# data/raw (kaggle CLI) or archive/ at the repo root (the zip extracted in place).
RAW = next((p for p in (HERE / "raw", HERE.parent / "archive") if p.exists()), HERE / "raw")
GOLDEN_PER_CLASS = 100
VAL_SHARE = 0.15


def find(split: str, cls: str) -> list[Path]:
    hits = sorted(RAW.rglob(f"{split}/{cls}/*.jpeg")) + sorted(RAW.rglob(f"{split}/{cls}/*.jpg"))
    # The archive also ships a 512x512 copy; keep the 300x300 casting_data tree only.
    return [p for p in hits if "casting_512x512" not in p.parts]


def main() -> None:
    rng = random.Random(42)
    mapping = {"ok_front": "ok", "def_front": "defective"}
    golden_rows = []
    for src, dst in mapping.items():
        test, train = find("test", src), find("train", src)
        if not test or not train:
            raise SystemExit(f"dataset not found under {RAW} (see the docstring)")
        rng.shuffle(test)
        for p in test[:GOLDEN_PER_CLASS]:
            out = HERE / "golden" / dst / p.name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            golden_rows.append({"path": f"{dst}/{p.name}", "label": dst, "defect_name": ""})
        rng.shuffle(train)
        n_val = int(len(train) * VAL_SHARE)
        for i, p in enumerate(train):
            split = "val" if i < n_val else "train"
            out = HERE / "splits" / "classify" / split / dst / p.name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
    with (HERE / "golden" / "manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "label", "defect_name"])
        w.writeheader()
        w.writerows(golden_rows)
    print(f"golden: {len(golden_rows)} images; splits written to data/splits/classify")
    # One upload for eval/train_yolo_colab.ipynb: the split plus the held-out golden set.
    bundle = HERE / "colab" / "senpaiqc_data.zip"
    bundle.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_STORED) as z:  # JPEGs do not compress further
        for sub in ("splits/classify", "golden"):
            for p in sorted((HERE / sub).rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(HERE).as_posix())
    print(f"colab bundle: {bundle} ({bundle.stat().st_size // 2**20} MB)")


if __name__ == "__main__":
    main()
