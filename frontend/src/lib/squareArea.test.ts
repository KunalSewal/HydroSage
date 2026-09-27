import { describe, expect, it } from 'vitest'
import { CLICK_SQUARE_HALF_DEG, squareAround } from './squareArea'

describe('squareAround', () => {
  it('returns a [lon, lat] square centred on the point', () => {
    const ring = squareAround(21.2, 81.3)

    expect(ring).toHaveLength(4)
    const lons = ring.map(([lon]) => lon)
    const lats = ring.map(([, lat]) => lat)
    expect(Math.min(...lons)).toBeCloseTo(81.3 - CLICK_SQUARE_HALF_DEG)
    expect(Math.max(...lons)).toBeCloseTo(81.3 + CLICK_SQUARE_HALF_DEG)
    expect(Math.min(...lats)).toBeCloseTo(21.2 - CLICK_SQUARE_HALF_DEG)
    expect(Math.max(...lats)).toBeCloseTo(21.2 + CLICK_SQUARE_HALF_DEG)
  })

  it('stays inside the backend area limit of 0.06 degrees per side', () => {
    expect(2 * CLICK_SQUARE_HALF_DEG).toBeLessThanOrEqual(0.06)
  })
})
