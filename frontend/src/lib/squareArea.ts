// A click on the map, in a deployment without the database-backed village
// flow (VITE_CLICK_ANALYZES_AREA), analyzes a square around the point
// through the same endpoint as a drawn area. ~2.2 km across: large enough
// to hold several farm-pond catchments, well inside the backend's 0.06 deg
// limit (backend app/domain/area.py).
export const CLICK_SQUARE_HALF_DEG = 0.01

export function squareAround(lat: number, lon: number, halfDeg = CLICK_SQUARE_HALF_DEG): [number, number][] {
  return [
    [lon - halfDeg, lat - halfDeg],
    [lon + halfDeg, lat - halfDeg],
    [lon + halfDeg, lat + halfDeg],
    [lon - halfDeg, lat + halfDeg],
  ]
}
