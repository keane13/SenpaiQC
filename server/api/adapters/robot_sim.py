"""Robot bridge: model function calls -> safety gate -> simulated SO-101 arm -> episode.

The simulator here is a scripted kinematic controller (joint-space interpolation between
named poses). It is the fallback the spec calls for; a LeRobot SO-101 simulation can
replace `_execute` behind the same port. Episodes are JSON so the web app can replay them.

The cell has one fixed camera and no renderer, so `second_look` is a digital zoom on the
region ER 2 pointed at; the wrist roll is replayed but the view is not re-rendered at that
angle. A real cell would capture a new frame here instead.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import cv2
import numpy as np

from domain.models import RobotCall
from domain.safety import gate
from ports import EpisodeRecord

# SO-101 joints: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll (deg), gripper (0-100)
POSES = {
    "home": [0, -90, 90, 0, 0, 0],
    "part": [0, -20, 60, -40, 0, 80],
    "camera": [-45, -50, 70, 0, 0, 0],
    "bin_pass": [60, -25, 55, -30, 0, 0],
    "bin_rework": [90, -25, 55, -30, 0, 0],
    "bin_scrap": [120, -25, 55, -30, 0, 0],
    "bin_hold": [145, -25, 55, -30, 0, 0],
}
JOINT_LIMITS = [(-150, 150), (-100, 100), (-100, 100), (-100, 100), (-180, 180), (0, 100)]
STEPS_PER_MOVE = 12
ZOOM_OUT_SIDE = 768  # px, longer side of the second-look view


class ScriptedSO101Sim:
    name = "scripted-kinematic-sim"

    def __init__(self, blobs):
        self.blobs = blobs

    def run(self, part_id: str, calls: list[RobotCall], scrap_confirmed: bool,
            on_present: Optional[Callable[[float], Optional[str]]] = None) -> EpisodeRecord:
        joints = list(POSES["home"])
        holding = False
        frames: list[dict] = []
        log: list[dict] = []
        blocked: list[dict] = []
        looked, reroute = False, None
        for call in calls:
            planned_bin = call.args.get("bin")
            if call.name == "place_in_bin" and reroute and planned_bin != reroute:
                call = RobotCall(name=call.name, args=call.args | {"bin": reroute})
            verdict = gate(call, {part_id}, scrap_confirmed)
            if not verdict.allowed:
                blocked.append({"call": call.model_dump(), "reason": verdict.reason})
                log.append({"call": call.model_dump(), "status": "blocked", "reason": verdict.reason})
                continue
            if call.name == "pick":
                joints = self._move(frames, joints, POSES["part"], call.name, holding)
                joints[5] = 20  # close gripper
                holding = True
            elif call.name == "present_to_camera":
                if not holding:
                    log.append({"call": call.model_dump(), "status": "skipped", "reason": "nothing held"})
                    continue
                target = list(POSES["camera"])
                target[4] = float(call.args["angle_deg"])
                joints = self._move(frames, joints, target, call.name, holding)
                if on_present and not looked:
                    looked = True
                    log.append({"call": call.model_dump(), "status": "done"})
                    reroute = on_present(float(call.args["angle_deg"]))
                    log.append({"call": {"name": "second_look", "args": {"angle_deg": call.args["angle_deg"]}},
                                "status": "done", **({"reason": f"disagrees with the first look: reroute to {reroute}"} if reroute else {})})
                    continue
            elif call.name == "place_in_bin":
                if not holding:
                    log.append({"call": call.model_dump(), "status": "skipped", "reason": "nothing held"})
                    continue
                joints = self._move(frames, joints, POSES[f"bin_{call.args['bin']}"], call.name, holding)
                joints[5] = 80  # open gripper
                holding = False
                if call.args["bin"] != planned_bin:
                    log.append({"call": call.model_dump(), "status": "done", "reason": f"rerouted from {planned_bin}"})
                    continue
            elif call.name == "stop":
                joints = self._move(frames, joints, POSES["home"], call.name, holding)
                log.append({"call": call.model_dump(), "status": "done"})
                break
            log.append({"call": call.model_dump(), "status": "done"})
        episode_id = f"ep-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        doc = {
            "episode_id": episode_id, "part_id": part_id, "simulator": self.name,
            "joint_names": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
            "log": log, "blocked": blocked, "frames": frames,
        }
        uri = self.blobs.save(f"episodes/{episode_id}.json", json.dumps(doc).encode(), "application/json")
        return EpisodeRecord(episode_id=episode_id, uri=uri, steps=log, blocked=blocked, simulator=self.name)

    def second_look(self, image: bytes, box: list[int], angle_deg: float) -> tuple[bytes, str]:
        arr = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        h, w = arr.shape[:2]
        x1, y1, x2, y2 = box
        # Square crop, 3x the defect box but at least a quarter of the frame, so the card's
        # surrounding context (hub, blade root, rim) stays in view.
        side = int(min(max(3 * max(x2 - x1, y2 - y1), min(w, h) // 4), min(w, h)))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        left, top = min(max(cx - side // 2, 0), w - side), min(max(cy - side // 2, 0), h - side)
        crop = arr[top:top + side, left:left + side]
        zoom = ZOOM_OUT_SIDE / side
        view = cv2.resize(crop, (ZOOM_OUT_SIDE, ZOOM_OUT_SIDE), interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise ValueError("could not encode the second-look view")
        how = (f"digital zoom x{zoom:.1f} on [{left}, {top}, {left + side}, {top + side}]; arm held the part at "
               f"{angle_deg:g} deg (simulated cell: one fixed camera, the angle is not re-rendered)")
        return buf.tobytes(), how

    @staticmethod
    def _move(frames: list[dict], start: list[float], target: list[float], action: str, holding: bool) -> list[float]:
        for i in range(1, STEPS_PER_MOVE + 1):
            t = i / STEPS_PER_MOVE
            q = [s + (e - s) * t for s, e in zip(start, target)]
            q = [max(lo, min(hi, v)) for v, (lo, hi) in zip(q, JOINT_LIMITS)]
            frames.append({"action": action, "q": [round(v, 2) for v in q], "holding": holding})
        return list(target)
