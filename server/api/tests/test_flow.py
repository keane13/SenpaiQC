"""End-to-end API flow with offline adapters (no Gemini key, no YOLO weights)."""
import json
import subprocess
import sys

from config import REPO_ROOT

from .conftest import jpeg_with_dark_spot


def _seed(client):
    from container import get_container
    from domain.models import DefectKnowledgeCard

    c = get_container()
    for d in json.loads((REPO_ROOT / "data" / "seed_cards.json").read_text()):
        c.cards.put(DefectKnowledgeCard(**d))
    return c


def test_auth_required(client):
    r = client.get("/api/teach/cards", headers={"Authorization": ""})
    assert r.status_code == 401


def test_teach_edit_resets_approval(client):
    _seed(client)
    r = client.put("/api/teach/cards/imp-200-burr-v1", json={"accept_limit": "flash under 0.2 mm"})
    assert r.json()["status"] == "draft"
    r = client.post("/api/teach/cards/imp-200-burr-v1/approve")
    assert r.json()["status"] == "approved" and r.json()["approved_by"] == "demo-inspector"


def test_teach_offline_gives_blank_card_that_cannot_be_approved(client):
    r = client.post("/api/teach/videos", data={"part_number": "IMP-200"},
                    files={"video": ("clip.mp4", b"\x00" * 100, "video/mp4")})
    card = r.json()["cards"][0]
    assert card["status"] == "draft"
    assert client.post(f"/api/teach/cards/{card['card_id']}/approve").status_code == 422


def test_inspect_escalates_and_confirm_writes_event(client):
    c = _seed(client)
    r = client.post("/api/inspect", data={"part_number": "IMP-200", "mould_id": "MD-04"},
                    files={"image": ("p.jpg", jpeg_with_dark_spot(), "image/jpeg")})
    res = r.json()
    assert res["path"] == "er2"  # no YOLO weights -> new part -> escalate
    assert res["needs_human_confirm"] is True
    assert res["defects"] and res["defects"][0]["point"]
    x, y = res["defects"][0]["point"]
    assert abs(x - 200) < 10 and abs(y - 90) < 10
    assert c.events.count() == 0  # nothing reaches BigQuery before the human confirms

    pending = client.get("/api/decisions?pending=true").json()
    assert [d["id"] for d in pending] == [res["id"]]
    r = client.post(f"/api/decisions/{res['id']}/confirm", json={"decision": "rework", "defect_name": "porosity"})
    assert r.json()["confirmed"] is True
    assert c.events.count() == 1

    g = client.get(f"/api/act/guide/{res['id']}?lang=id").json()
    assert g["steps"] and g["decision"] == "rework"

    ep = client.post(f"/api/act/robot/{res['id']}").json()
    assert [s["call"]["name"] for s in ep["log"]] == ["pick", "present_to_camera", "second_look", "place_in_bin", "stop"]
    assert [s["status"] for s in ep["log"]] == ["done"] * 5
    # The planner took its angle from the cited card's inspection_view (porosity: 30 deg).
    assert ep["calls"][1]["args"]["angle_deg"] == 30
    sl = ep["second_look"]
    assert sl["status"] == "done" and sl["agrees"] is True
    assert sl["before"]["decision"] == sl["after"]["decision"] == "rework"
    assert client.get("/api/act/second-look/stats").json()["n"] == 1
    img = client.get(f"/api/act/second-look/{ep['episode_id']}/image?token=senpaiqc-demo")
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"  # JPEG
    frames = client.get(f"/api/act/episodes/{ep['episode_id']}").json()["frames"]
    assert len(frames) > 10

    exp = client.post("/api/learn/labels/export?part_number=IMP-200").json()
    assert exp["count"] == 1


def test_robot_gate_blocks_unconfirmed_scrap(client, monkeypatch):
    _seed(client)
    res = client.post("/api/inspect", data={"part_number": "IMP-200"},
                      files={"image": ("p.jpg", jpeg_with_dark_spot(), "image/jpeg")}).json()
    from container import get_container
    from ports import ModelUsage, ReasoningOutput

    c = get_container()
    # The second look agrees, so the planned scrap reaches the gate (instead of being held).
    monkeypatch.setattr(c.reasoning, "inspect", lambda *a, **k: ReasoningOutput(
        defects=[], decision="scrap", rationale="crack on the rim", needs_human_confirm=True,
        usage=ModelUsage(model="stub")))
    d = c.docs.get("decisions", res["id"])
    d["decision"] = "scrap"
    c.docs.put("decisions", res["id"], d)
    ep = client.post(f"/api/act/robot/{res['id']}").json()
    assert any("scrap requires a human confirm" in b["reason"] for b in ep["blocked"])


def test_second_look_disagreement_reroutes_to_hold(client, monkeypatch):
    _seed(client)
    res = client.post("/api/inspect", data={"part_number": "IMP-200"},
                      files={"image": ("p.jpg", jpeg_with_dark_spot(), "image/jpeg")}).json()
    from container import get_container
    from ports import ModelUsage, ReasoningOutput

    c = get_container()
    monkeypatch.setattr(c.reasoning, "inspect", lambda *a, **k: ReasoningOutput(
        defects=[], decision="pass", rationale="closer view: clean surface", needs_human_confirm=False,
        usage=ModelUsage(model="stub"), confidence=0.9))
    ep = client.post(f"/api/act/robot/{res['id']}").json()
    assert ep["second_look"]["agrees"] is False
    place = next(s for s in ep["log"] if s["call"]["name"] == "place_in_bin")
    assert place["call"]["args"]["bin"] == "hold" and "rerouted from rework" in place["reason"]
    d = c.docs.get("decisions", res["id"])
    assert d["decision"] == "rework" and d["needs_human_confirm"] is True  # the person decides, not the robot
    stats = client.get("/api/act/second-look/stats").json()
    assert stats["rerouted_to_hold"] == 1 and stats["needs_human_after"] == 0.0


def _load_process_events(c) -> list:
    """Synthetic process history with the planted cause, written to the event store."""
    subprocess.run([sys.executable, str(REPO_ROOT / "data" / "generate_process.py")], check=True, capture_output=True)
    import csv
    from datetime import datetime

    from domain.models import InspectionEvent

    with (REPO_ROOT / "data" / "process_events.csv").open() as f:
        rows = [InspectionEvent(**(r | {"event_ts": datetime.fromisoformat(r["event_ts"]),
                                        "defect_name": r["defect_name"] or None,
                                        "confirmed": r["confirmed"] == "True"})) for r in csv.DictReader(f)]
    c.events.write_many(rows)
    return rows


def test_spc_scan_and_root_cause_find_planted_cause(client, tmp_path):
    c = _seed(client)
    rows = _load_process_events(c)
    invs = client.post("/api/learn/scan", json={}).json()
    assert [i["defect_name"] for i in invs] == ["porosity"]
    inv = client.post(f"/api/learn/investigations/{invs[0]['id']}/analyse").json()
    truth = json.loads((REPO_ROOT / "data" / "planted_cause.json").read_text())
    assert inv["hypotheses"][0]["blamed"] == {"mould_id": truth["mould_id"], "material_lot": truth["material_lot"]}
    rep = client.get(f"/api/learn/reports/{inv['report_id']}").json()
    assert rep["status"] == "draft" and set(rep["sections"]) >= {"D1_team", "D8_recognition"}
    rep = client.put(f"/api/learn/reports/{inv['report_id']}", json={"sections": {"D5_corrective_actions": "Replace lot"}, "approve": True}).json()
    assert rep["status"] == "approved" and rep["sections"]["D5_corrective_actions"] == "Replace lot"
    dash = client.get("/api/learn/dashboard").json()
    assert dash["synthetic"]["parts"] == len(rows)
    assert dash["measured"]["parts"] == 0
