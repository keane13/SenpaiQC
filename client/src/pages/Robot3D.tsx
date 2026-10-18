/**
 * 3D replay of a robot-cell episode (Three.js). Visualises the same joint angles as the 2D
 * replay: it is the scripted kinematic simulation, not a physics simulation.
 *
 * Geometry follows the simulator's conventions (server/api/adapters/robot_sim.py):
 *   q = [shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper] in degrees
 *   pan 0 = tray, -45 = camera, bins at 60 / 90 / 120 / 145
 *   in the arm plane: upper arm at -lift from horizontal, elbow and wrist relative to it.
 */
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface Frame { action: string; q: number[]; holding: boolean }
type View = "orbit" | "top" | "camera";

const DEG = Math.PI / 180;
const SHOULDER_H = 0.7, L1 = 1.1, L2 = 0.9, L3 = 0.35;
const CELL_R = 1.95;
const BINS: Record<string, { deg: number; color: number; label: string }> = {
  pass: { deg: 60, color: 0x1e7b34, label: "PASS" },
  rework: { deg: 90, color: 0xf2b705, label: "REWORK" },
  scrap: { deg: 120, color: 0xb42318, label: "SCRAP" },
  hold: { deg: 145, color: 0x475569, label: "HOLD" },
};
const TRAY_DEG = 0, CAMERA_DEG = -45;

/** Direction on the table for a pan angle (0 = tray, towards -Z). */
const dir = (deg: number) => new THREE.Vector3(Math.sin(deg * DEG), 0, -Math.cos(deg * DEG));

function label(text: string, color: string): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 96;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(255,255,255,.92)";
  g.beginPath(); g.roundRect(8, 14, 240, 68, 12); g.fill();
  g.fillStyle = color;
  g.font = "600 52px 'Barlow Condensed', 'Arial Narrow', sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 128, 50);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  s.scale.set(0.78, 0.29, 1);
  return s;
}

function bin(color: number): THREE.Group {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05 });
  const w = 0.62, h = 0.32, t = 0.03;
  const floor = new THREE.Mesh(new THREE.BoxGeometry(w, t, w), mat);
  floor.position.y = t / 2;
  g.add(floor);
  for (const [x, z, sx, sz] of [[0, w / 2, w, t], [0, -w / 2, w, t], [w / 2, 0, t, w], [-w / 2, 0, t, w]]) {
    const wall = new THREE.Mesh(new THREE.BoxGeometry(sx, h, sz), mat);
    wall.position.set(x, h / 2, z);
    g.add(wall);
  }
  g.traverse((o) => { o.castShadow = true; o.receiveShadow = true; });
  return g;
}

function impeller(): THREE.Group {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: 0x9aa4ad, roughness: 0.35, metalness: 0.75 });
  const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.04, 40), mat);
  g.add(disc);
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.09, 24), mat);
  hub.position.y = 0.045;
  g.add(hub);
  for (let k = 0; k < 6; k++) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.05, 0.018), mat);
    const a = (k / 6) * Math.PI * 2;
    blade.position.set(Math.cos(a) * 0.09, 0.04, Math.sin(a) * 0.09);
    blade.rotation.y = -a + 0.5;
    g.add(blade);
  }
  g.traverse((o) => { o.castShadow = true; });
  g.userData.material = mat;
  return g;
}

/** Where the part is at frame i: in the gripper, on the tray, or in the bin it was released over. */
function partState(frames: Frame[], i: number): { where: "gripper" | "tray" | "bin"; binDeg?: number } {
  if (frames[i]?.holding) return { where: "gripper" };
  for (let k = i; k > 0; k--) {
    if (frames[k - 1].holding && !frames[k].holding) return { where: "bin", binDeg: frames[k - 1].q[0] };
  }
  return { where: "tray" };
}

function nearestBin(deg: number): string {
  return Object.entries(BINS).reduce((best, [k, b]) => (Math.abs(b.deg - deg) < Math.abs(BINS[best].deg - deg) ? k : best), "pass");
}

export default function Robot3D({ frames, index, blockedBins }: { frames: Frame[]; index: number; blockedBins: string[] }) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ setFrame: (i: number) => void; setView: (v: View) => void } | null>(null);
  const [view, setView] = useState<View>("orbit");
  const [follow, setFollow] = useState(true);
  const followRef = useRef(follow);
  followRef.current = follow;

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    cam.position.set(1.4, 3.7, 5.3);
    const controls = new OrbitControls(cam, renderer.domElement);
    controls.target.set(0, 0.55, -0.3);
    controls.enableDamping = true;
    controls.minDistance = 2.5;
    controls.maxDistance = 11;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.addEventListener("start", () => setFollow(false));

    // Studio light: sky-tinted ambient, one soft key light with shadows, a cool rim light.
    scene.add(new THREE.HemisphereLight(0xe8f4fc, 0xb8c3cc, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(3.5, 6, 2.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4 });
    key.shadow.radius = 4;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x9fd3dc, 0.8);
    rim.position.set(-4, 3, -3);
    scene.add(rim);

    // Work table.
    const table = new THREE.Mesh(new THREE.CylinderGeometry(3.1, 3.1, 0.12, 96),
      new THREE.MeshStandardMaterial({ color: 0xf3f6f8, roughness: 0.85 }));
    table.position.y = -0.06;
    table.receiveShadow = true;
    scene.add(table);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(3.1, 0.02, 8, 128), new THREE.MeshStandardMaterial({ color: 0x0e7c86, roughness: 0.4 }));
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);

    // Tray, camera station and bins around the arm.
    const tray = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.05, 0.6), new THREE.MeshStandardMaterial({ color: 0x5d6a75, roughness: 0.6 }));
    tray.position.copy(dir(TRAY_DEG).multiplyScalar(1.8)).setY(0.025);
    tray.receiveShadow = tray.castShadow = true;
    scene.add(tray);
    const trayLabel = label("TRAY", "#34414d");
    trayLabel.position.copy(dir(TRAY_DEG).multiplyScalar(2.35)).setY(0.35);
    scene.add(trayLabel);

    const station = new THREE.Group();
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.05, 16), new THREE.MeshStandardMaterial({ color: 0x34414d, metalness: 0.5, roughness: 0.4 }));
    post.position.y = 0.525;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.2, 0.22), new THREE.MeshStandardMaterial({ color: 0x16212b, roughness: 0.5 }));
    body.position.y = 1.12;
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.08, 24), new THREE.MeshStandardMaterial({ color: 0x0e7c86, metalness: 0.6, roughness: 0.2 }));
    lens.rotation.x = Math.PI / 2;
    lens.position.set(0, 1.12, -0.15);
    station.add(post, body, lens);
    station.traverse((o) => { o.castShadow = true; });
    const camPos = dir(CAMERA_DEG).multiplyScalar(2.65);
    station.position.copy(camPos);
    station.lookAt(new THREE.Vector3(0, 0, 0));
    station.rotateY(Math.PI);
    scene.add(station);
    const camLabel = label("CAMERA", "#0e7c86");
    camLabel.position.copy(camPos).setY(1.5);
    scene.add(camLabel);

    const binMeshes: Record<string, THREE.Group> = {};
    for (const [k, b] of Object.entries(BINS)) {
      const g = bin(b.color);
      g.position.copy(dir(b.deg).multiplyScalar(CELL_R));
      g.lookAt(new THREE.Vector3(0, 0, 0));
      scene.add(g);
      binMeshes[k] = g;
      const l = label(b.label, "#" + b.color.toString(16).padStart(6, "0"));
      l.position.copy(dir(b.deg).multiplyScalar(CELL_R + 0.5)).setY(0.55);
      scene.add(l);
    }

    // SO-101-like arm: base -> pan -> shoulder -> elbow -> wrist flex -> wrist roll -> gripper.
    const shell = new THREE.MeshStandardMaterial({ color: 0xf6f8fa, roughness: 0.35, metalness: 0.1 });
    const joint = new THREE.MeshStandardMaterial({ color: 0x0e7c86, roughness: 0.35, metalness: 0.3 });
    const dark = new THREE.MeshStandardMaterial({ color: 0x24303b, roughness: 0.5, metalness: 0.4 });
    const shadowed = (m: THREE.Mesh) => { m.castShadow = true; m.receiveShadow = true; return m; };
    const link = (len: number, r: number) => {
      const m = shadowed(new THREE.Mesh(new THREE.CapsuleGeometry(r, len - 2 * r, 8, 20), shell));
      m.rotation.x = Math.PI / 2;
      m.position.z = -len / 2;
      return m;
    };
    const servo = (r: number) => {
      const m = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(r, r, r * 1.6, 24), joint));
      m.rotation.z = Math.PI / 2;
      return m;
    };

    const base = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.4, 0.22, 40), dark));
    base.position.y = 0.11;
    scene.add(base);
    const pan = new THREE.Group();
    pan.position.y = 0.22;
    scene.add(pan);
    const tower = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.2, SHOULDER_H - 0.22, 32), shell));
    tower.position.y = (SHOULDER_H - 0.22) / 2;
    pan.add(tower);
    const shoulder = new THREE.Group();
    shoulder.position.y = SHOULDER_H - 0.22;
    shoulder.add(servo(0.13));
    shoulder.add(link(L1, 0.09));
    pan.add(shoulder);
    const elbow = new THREE.Group();
    elbow.position.z = -L1;
    elbow.add(servo(0.11));
    elbow.add(link(L2, 0.075));
    shoulder.add(elbow);
    const wrist = new THREE.Group();
    wrist.position.z = -L2;
    wrist.add(servo(0.085));
    elbow.add(wrist);
    const roll = new THREE.Group();
    wrist.add(roll);
    const palm = shadowed(new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.08, 0.16), dark));
    palm.position.z = -0.12;
    roll.add(palm);
    const fingerGeo = new THREE.BoxGeometry(0.03, 0.06, L3 - 0.2);
    const fingerL = shadowed(new THREE.Mesh(fingerGeo, dark));
    const fingerR = shadowed(new THREE.Mesh(fingerGeo, dark));
    fingerL.position.z = fingerR.position.z = -0.2 - (L3 - 0.2) / 2;
    roll.add(fingerL, fingerR);
    const tip = new THREE.Object3D();
    tip.position.z = -L3 + 0.04;
    roll.add(tip);

    const part = impeller();
    scene.add(part);
    const partMat = part.userData.material as THREE.MeshStandardMaterial;

    // Views.
    const views: Record<View, { pos: THREE.Vector3; target: THREE.Vector3 }> = {
      orbit: { pos: new THREE.Vector3(1.4, 3.7, 5.3), target: new THREE.Vector3(0, 0.55, -0.3) },
      top: { pos: new THREE.Vector3(0.01, 8.5, 0.6), target: new THREE.Vector3(0, 0, 0) },
      // side-on to the arm and the camera station, so the presented part is in view
      camera: { pos: dir(CAMERA_DEG - 75).multiplyScalar(4.3).setY(2.1), target: dir(CAMERA_DEG).multiplyScalar(2.0).setY(0.95) },
    };
    let goal = views.orbit;
    let blink: THREE.Group | null = null;
    let current = 0;

    const setFrame = (i: number) => {
      current = i;
      const f = frames[Math.min(i, frames.length - 1)];
      const [p, lift, elb, wfl, wrl, grip] = f.q;
      const a1 = -lift * DEG, a2 = a1 - elb * DEG, a3 = a2 + wfl * DEG;
      pan.rotation.y = -p * DEG;
      shoulder.rotation.x = a1;
      elbow.rotation.x = a2 - a1;
      wrist.rotation.x = a3 - a2;
      roll.rotation.z = wrl * DEG;
      const open = 0.03 + (grip / 100) * 0.07;
      fingerL.position.x = -open;
      fingerR.position.x = open;

      const st = partState(frames, i);
      if (st.where === "gripper") {
        scene.updateMatrixWorld();
        tip.getWorldPosition(part.position);
        part.position.y -= 0.02;
        partMat.color.setHex(0x9aa4ad);
      } else if (st.where === "bin") {
        const k = nearestBin(st.binDeg ?? 60);
        part.position.copy(dir(BINS[k].deg).multiplyScalar(CELL_R)).setY(0.07);
        partMat.color.setHex(BINS[k].color).lerp(new THREE.Color(0x9aa4ad), 0.35);
      } else {
        part.position.copy(dir(TRAY_DEG).multiplyScalar(1.8)).setY(0.07);
        partMat.color.setHex(0x9aa4ad);
      }
      if (followRef.current) goal = f.action === "present_to_camera" || f.action === "second_look" ? views.camera : views.orbit;
    };
    const setViewFn = (v: View) => { goal = views[v]; };
    api.current = { setFrame, setView: setViewFn };
    setFrame(index);

    // A blocked call (e.g. scrap before a human confirm) makes its bin pulse.
    blink = blockedBins.length ? binMeshes[blockedBins[0]] ?? null : null;

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    let raf = 0;
    const clock = new THREE.Clock();
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const t = clock.getElapsedTime();
      if (goal) {
        cam.position.lerp(goal.pos, 0.06);
        controls.target.lerp(goal.target, 0.06);
        if (cam.position.distanceTo(goal.pos) < 0.01) goal = null as unknown as typeof goal;
      }
      if (blink) {
        const s = 1 + Math.max(0, Math.sin(t * 6)) * 0.06;
        blink.scale.setScalar(s);
      }
      if (partState(frames, current).where === "gripper") part.rotation.y += 0.01;
      controls.update();
      renderer.render(scene, cam);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
        mats.forEach((x: THREE.Material & { map?: THREE.Texture }) => { x.map?.dispose(); x.dispose(); });
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      api.current = null;
    };
    // The scene is rebuilt only when the episode changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, blockedBins.join(",")]);

  useEffect(() => { api.current?.setFrame(index); }, [index]);

  const choose = (v: View) => { setView(v); setFollow(false); api.current?.setView(v); };

  return (
    <div style={{ position: "relative" }}>
      <div ref={host} className="robot-3d" role="img"
        aria-label={`3D replay, frame ${index + 1} of ${frames.length}: ${frames[index]?.action}. Drag to rotate, scroll to zoom.`} />
      <div className="robot-3d-views" role="group" aria-label="Camera view">
        {(["orbit", "top", "camera"] as View[]).map((v) => (
          <button key={v} aria-pressed={view === v && !follow} onClick={() => choose(v)}>
            {v === "orbit" ? "3D" : v === "top" ? "Top" : "Camera"}
          </button>
        ))}
        <button aria-pressed={follow} onClick={() => setFollow(!follow)} title="Move the view with the action (closer look at the camera station)">Follow</button>
      </div>
      <div className="robot-3d-legend">Drag to rotate · scroll to zoom · simulated cell</div>
    </div>
  );
}
