import { describe, expect, it } from 'vitest'
import { resolveFocusBounds } from './mapFocus'

const bbox = { min_lon: 80.0, min_lat: 21.0, max_lon: 80.5, max_lat: 21.5 }

describe('resolveFocusBounds', () => {
  it('returns null when there is nothing to focus on', () => {
    expect(resolveFocusBounds(null, null)).toBeNull()
  })

  it('falls back to the source bounding box when no catchment has been traced', () => {
    expect(resolveFocusBounds(null, bbox)).toEqual([
      [21.0, 80.0],
      [21.5, 80.5],
    ])
  })

  // The catchment is the answer the user asked for; the source bbox is the
  // whole surveyed sheet, which for the sample KML is ~60x the catchment.
  it('prefers the catchment over the source bounding box', () => {
    const boundary: [number, number][] = [
      [80.20, 21.20],
      [80.24, 21.20],
      [80.24, 21.23],
      [80.20, 21.23],
    ]
    expect(resolveFocusBounds(boundary, bbox)).toEqual([
      [21.2, 80.2],
      [21.23, 80.24],
    ])
  })

  // Boundary rings arrive as [lon, lat] (GeoJSON order) but Leaflet wants
  // [lat, lng] -- swapping these silently sends the map to the wrong hemisphere.
  it('converts the boundary from [lon, lat] to Leaflet [lat, lng] order', () => {
    const boundary: [number, number][] = [
      [80.1, 21.9],
      [80.3, 21.7],
    ]
    expect(resolveFocusBounds(boundary, null)).toEqual([
      [21.7, 80.1],
      [21.9, 80.3],
    ])
  })

  it('ignores an empty boundary ring and falls back to the bounding box', () => {
    expect(resolveFocusBounds([], bbox)).toEqual([
      [21.0, 80.0],
      [21.5, 80.5],
    ])
  })
})
