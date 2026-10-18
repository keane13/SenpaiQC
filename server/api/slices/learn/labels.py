"""Teacher-student loop: export inspector-confirmed ER 2 decisions as YOLO labels."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def export_labels(c, part_number: str) -> dict:
    """Write an Ultralytics dataset (classification folders + detection txt) to the blob store.

    Only decisions a human confirmed are exported (golden rule: labels need a human).
    """
    decisions = [d for d in c.docs.list("decisions", 5000)
                 if d.get("confirmed") and d["path"] == "er2" and d["part_number"] == part_number]
    classes = ["ok"] + sorted({card.defect_name for card in c.cards.list(part_number=part_number, status="approved")})
    stamp = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    root = f"labels/{part_number}/{stamp}"
    manifest = []
    for d in decisions:
        name = _label_name(c, d)
        if name not in classes:
            continue
        image = c.blobs.load(d["image_uri"])
        c.blobs.save(f"{root}/classify/{name}/{d['id']}.jpg", image, "image/jpeg")
        c.blobs.save(f"{root}/detect/images/{d['id']}.jpg", image, "image/jpeg")
        w, h = d.get("image_size") or [0, 0]
        lines = []
        if name != "ok" and w and h:
            for f in d.get("defects", []):
                if len(f.get("box") or []) == 4:
                    x1, y1, x2, y2 = f["box"]
                    lines.append(f"{classes.index(name)} {((x1 + x2) / 2) / w:.6f} {((y1 + y2) / 2) / h:.6f} "
                                 f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        c.blobs.save(f"{root}/detect/labels/{d['id']}.txt", "\n".join(lines).encode(), "text/plain")
        manifest.append({"decision_id": d["id"], "label": name, "boxes": len(lines), "confirmed_by": d.get("confirmed_by")})
    yaml = "path: .\ntrain: images\nval: images\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(classes))
    c.blobs.save(f"{root}/detect/data.yaml", yaml.encode(), "text/yaml")
    uri = c.blobs.save(f"{root}/manifest.json", json.dumps({"classes": classes, "items": manifest}, indent=1).encode(),
                       "application/json")
    return {"uri": uri, "count": len(manifest), "classes": classes}


def _label_name(c, d: dict) -> str:
    if d["decision"] == "pass":
        return "ok"
    if d.get("confirmed_defect_name"):
        return d["confirmed_defect_name"]
    for f in d.get("defects", []):
        if f.get("card_id"):
            card = c.cards.get(f["card_id"])
            if card:
                return card.defect_name
    return "unknown"
