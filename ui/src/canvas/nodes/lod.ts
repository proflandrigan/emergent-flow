// Pure level-of-detail (LOD) policy for canvas nodes, kept free of React Flow so it is
// unit-testable in isolation. EfNode.tsx selects a BOOLEAN from this helper (not the raw zoom)
// via `useStore` so a node only re-renders when it crosses the threshold.

// Below this zoom, nodes render in low-detail mode (heavy in-node views suppressed). 1.0 is the
// default/fit zoom; 0.4 ≈ "zoomed out far enough that per-node detail isn't legible anyway".
export const LOD_ZOOM_THRESHOLD = 0.4;

export function isDetailed(zoom: number): boolean {
  return zoom >= LOD_ZOOM_THRESHOLD;
}
