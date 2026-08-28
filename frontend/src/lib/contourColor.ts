// Hypsometric-style ramp (the same idea real topo maps use): low elevation
// reads as cool green, high elevation as warm red/brown, so distinct
// elevation bands are visible at a glance instead of one flat line color.
const RAMP: Array<[number, [number, number, number]]> = [
  [0, [34, 197, 94]], // green-500
  [0.35, [234, 179, 8]], // yellow-500
  [0.65, [249, 115, 22]], // orange-500
  [1, [185, 28, 28]], // red-700
]

export function contourColor(elevation: number, min: number, max: number): string {
  if (max <= min) return rgbToCss(RAMP[0][1])
  const t = Math.min(1, Math.max(0, (elevation - min) / (max - min)))

  for (let i = 1; i < RAMP.length; i++) {
    const [t0, c0] = RAMP[i - 1]
    const [t1, c1] = RAMP[i]
    if (t <= t1) {
      const localT = t1 === t0 ? 0 : (t - t0) / (t1 - t0)
      return rgbToCss(lerp(c0, c1, localT))
    }
  }
  return rgbToCss(RAMP[RAMP.length - 1][1])
}

function lerp(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

function rgbToCss([r, g, b]: [number, number, number]): string {
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}
