# Models

`best.pt` is the YOLO11n classification model used as the fast path (ok vs defective, pump
impellers, 224 px, 15 epochs, validation top-1 99.7%, see `eval/results/yolo_baseline.json`).
The Dockerfile bakes it into the image. `label_counts.json` holds the labelled-image count per part
number, which the escalation policy uses to decide when a part is still "new".

Retrain with `eval/train_yolo.py` or `eval/train_yolo_colab.ipynb`.
Ultralytics YOLO is AGPL-3.0.
