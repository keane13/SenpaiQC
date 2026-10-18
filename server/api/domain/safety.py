"""Robot safety gate. Every function call from the model passes through here first."""
from __future__ import annotations

from .models import GateVerdict, RobotCall

ALLOWED_FUNCTIONS = {"pick", "present_to_camera", "place_in_bin", "stop"}
ALLOWED_BINS = {"pass", "rework", "scrap", "hold"}  # hold = a person decides (second look disagreed)
ANGLE_LIMITS = (-90.0, 90.0)


def gate(call: RobotCall, valid_part_ids: set[str], scrap_confirmed: bool) -> GateVerdict:
    def deny(reason: str) -> GateVerdict:
        return GateVerdict(call=call, allowed=False, reason=reason)

    if call.name not in ALLOWED_FUNCTIONS:
        return deny(f"function {call.name!r} not allowed")
    if call.name == "stop":
        return GateVerdict(call=call, allowed=True)
    part_id = call.args.get("part_id")
    if part_id not in valid_part_ids:
        return deny(f"unknown part_id {part_id!r}")
    if call.name == "present_to_camera":
        try:
            angle = float(call.args.get("angle_deg"))
        except (TypeError, ValueError):
            return deny("angle_deg missing or not a number")
        if not ANGLE_LIMITS[0] <= angle <= ANGLE_LIMITS[1]:
            return deny(f"angle_deg {angle} outside workspace limits {ANGLE_LIMITS}")
    if call.name == "place_in_bin":
        bin_ = call.args.get("bin")
        if bin_ not in ALLOWED_BINS:
            return deny(f"bin {bin_!r} not in {sorted(ALLOWED_BINS)}")
        if bin_ == "scrap" and not scrap_confirmed:
            return deny("scrap requires a human confirm first")
    return GateVerdict(call=call, allowed=True)
