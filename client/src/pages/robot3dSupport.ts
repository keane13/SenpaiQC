let cached: boolean | null = null;

/** True when the browser can render WebGL; otherwise the robot replay stays 2D.
 *  Checked once: browsers allow only a few live WebGL contexts, so the probe context is released. */
export function webglAvailable(): boolean {
  if (cached !== null) return cached;
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
    cached = !!gl;
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    cached = false;
  }
  return cached;
}
