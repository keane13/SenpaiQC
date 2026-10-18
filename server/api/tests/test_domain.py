import pytest

from adapters.sql_templates import render
from domain.geometry import box1000_to_px, yx1000_to_px
from domain.models import Decision, DefectKnowledgeCard, RobotCall
from domain.policy import EscalationPolicy, needs_confirm, yolo_decision
from domain.safety import gate
from domain.spc import Subgroup, p_chart

P = EscalationPolicy(0.85, 0.40, 50)
KNOWN = {"ok", "porosity"}


@pytest.mark.parametrize("cls,conf,labels,path", [
    ("ok", 0.95, 1000, "yolo"),
    ("porosity", 0.85, 1000, "yolo"),
    ("porosity", 0.62, 1000, "er2"),
    ("porosity", 0.20, 1000, "er2"),
    ("blowhole", 0.99, 1000, "er2"),
    (None, 0.0, 1000, "er2"),
    ("ok", 0.99, 10, "er2"),
])
def test_escalation_policy(cls, conf, labels, path):
    assert P.route(cls, conf, KNOWN, labels)[0] == path


def test_yolo_decision_uses_card_severity():
    crack = DefectKnowledgeCard(card_id="c", part_number="P", defect_name="crack", severity="critical")
    assert yolo_decision("ok", []) == Decision.pass_
    assert yolo_decision("crack", [crack]) == Decision.scrap
    assert yolo_decision("porosity", [crack]) == Decision.rework


def test_scrap_always_needs_confirm():
    assert needs_confirm(Decision.scrap, False, False)
    assert needs_confirm(Decision.rework, True, False)
    assert not needs_confirm(Decision.pass_, False, False)


def test_er2_coordinates_convert_to_pixel_xy():
    assert yx1000_to_px([500, 250], 800, 600) == [200, 300]
    assert box1000_to_px([100, 200, 300, 400], 1000, 500) == [200, 50, 400, 150]


def test_p_chart_flags_spike_with_baseline():
    sg = [Subgroup(f"d{i}", 400, 12) for i in range(20)] + [Subgroup("spike", 400, 40)]
    pts = p_chart(sg, baseline=20)
    assert not any(p.out_of_control for p in pts[:20])
    assert pts[-1].out_of_control


@pytest.mark.parametrize("call,ok", [
    (RobotCall(name="pick", args={"part_id": "p1"}), True),
    (RobotCall(name="pick", args={"part_id": "p2"}), False),
    (RobotCall(name="rm_rf", args={}), False),
    (RobotCall(name="place_in_bin", args={"part_id": "p1", "bin": "floor"}), False),
    (RobotCall(name="place_in_bin", args={"part_id": "p1", "bin": "scrap"}), False),
    (RobotCall(name="place_in_bin", args={"part_id": "p1", "bin": "hold"}), True),
    (RobotCall(name="present_to_camera", args={"part_id": "p1", "angle_deg": 170}), False),
    (RobotCall(name="present_to_camera", args={"part_id": "p1", "angle_deg": 30}), True),
    (RobotCall(name="stop", args={}), True),
])
def test_safety_gate(call, ok):
    assert gate(call, {"p1"}, scrap_confirmed=False).allowed is ok


def test_sql_templates_reject_unlisted_dimension():
    with pytest.raises(ValueError):
        render("rate_by_dim", "sqlite", "t", "1; DROP TABLE t")
    with pytest.raises(ValueError):
        render("delete_all", "sqlite", "t")


def test_label_counts_accept_inline_json_or_file(tmp_path):
    from adapters.yolo import load_label_counts

    assert load_label_counts("") == {}
    assert load_label_counts('{"IMP-200": 5639}') == {"IMP-200": 5639}
    f = tmp_path / "counts.json"
    f.write_text('{"IMP-200": "12"}')
    assert load_label_counts(str(f)) == {"IMP-200": 12}
