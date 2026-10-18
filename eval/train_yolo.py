"""Train the YOLO fast path (classification, CPU-friendly nano model).

  pip install ultralytics
  python eval/train_yolo.py                        # baseline on data/splits/classify
  python eval/train_yolo.py --extra <labels-export-dir>/classify --name retrain   # teacher-student

Writes runs/<name>/weights/best.pt and eval/results/yolo_<name>.json (val metrics).
Run on Colab with a GPU for speed; the API serves the weights on Cloud Run CPU.
The class "defective" is renamed to the card's defect name only if the export provides it.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="baseline")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--extra", default=None, help="classify/ folder from a confirmed-label export")
    a = ap.parse_args()
    from ultralytics import YOLO

    data = ROOT / "data" / "splits" / "classify"
    if a.extra:
        # Merge inspector-confirmed ER 2 labels into a copy of the training split.
        merged = ROOT / "data" / "splits" / f"classify_{a.name}"
        if merged.exists():
            shutil.rmtree(merged)
        shutil.copytree(data, merged)
        for img in Path(a.extra).rglob("*.jpg"):
            cls = img.parent.name
            cls = "ok" if cls == "ok" else "defective"
            dst = merged / "train" / cls / f"confirmed_{img.name}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dst)
        data = merged
    model = YOLO("yolo11n-cls.pt")
    model.train(data=str(data), epochs=a.epochs, imgsz=224, project=str(ROOT / "runs"), name=a.name, exist_ok=True)
    metrics = model.val(data=str(data), split="val")
    out = {"name": a.name, "top1": float(metrics.top1), "weights": str(ROOT / "runs" / a.name / "weights" / "best.pt")}
    (ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "eval" / "results" / f"yolo_{a.name}.json").write_text(json.dumps(out, indent=2))
    print(out)


if __name__ == "__main__":
    main()
