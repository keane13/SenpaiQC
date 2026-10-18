# Robot simulation

The robot bridge is the `RobotBridge` port. The shipped implementation is
`server/api/adapters/robot_sim.py`: a **scripted kinematic SO-101 controller**, the fallback the
spec names for when the learned policy is not ready. It interpolates joint-space waypoints between
named poses (tray, camera, three bins, home), clamps them to joint limits, and records each frame
as episode JSON in Cloud Storage. The web app replays episodes on the Robot tab.

Every call from Gemini Robotics ER 2 passes `domain/safety.py` before execution:
- only `pick`, `present_to_camera`, `place_in_bin` and `stop` are allowed
- `part_id` must be the part under inspection
- `bin` must be one of pass, rework, scrap or hold (hold = a person decides after the two looks disagree)
- `angle_deg` must be within ±90°
- scrap is allowed only after a human has confirmed the decision

Second look: the cell has one fixed camera and no renderer, so `second_look(image, box, angle)` is a
digital zoom on the region ER 2 pointed at. The wrist roll is replayed but the view is not
re-rendered at that angle. A real arm adapter captures a fresh frame there instead.

To plug in a LeRobot SO-101 simulation, implement `run(part_id, calls, scrap_confirmed, on_present)`
and `second_look(image, box, angle_deg)` in a new adapter. Keep the safety gate call, record the episode the same way, and select the adapter in
`container.py`. Check the current LeRobot SO-101 simulation environment name in its docs first.
