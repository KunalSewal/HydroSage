import type { BoundingBox } from '../api/client'

// Leaflet's LatLngBoundsExpression in its [[south, west], [north, east]] form.
export type FocusBounds = [[number, number], [number, number]]

// Decides what the map should frame once an analysis resolves.
//
// The catchment wins over the source bounding box whenever we have one: the
// bbox covers the whole surveyed sheet, which for the sample KML is roughly
// sixty times the area of the catchment it contains, so fitting to it leaves
// the actual answer as a speck in the middle.
//
// Kept apart from MapView so the decision is testable without standing up
// Leaflet in jsdom.
export function resolveFocusBounds(
  catchmentBoundary: [number, number][] | null | undefined,
  sourceBbox: BoundingBox | null | undefined,
): FocusBounds | null {
  if (catchmentBoundary && catchmentBoundary.length > 0) {
    // Rings arrive as [lon, lat] (GeoJSON order); Leaflet wants [lat, lng].
    const lons = catchmentBoundary.map(([lon]) => lon)
    const lats = catchmentBoundary.map(([, lat]) => lat)
    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ]
  }

  if (sourceBbox) {
    return [
      [sourceBbox.min_lat, sourceBbox.min_lon],
      [sourceBbox.max_lat, sourceBbox.max_lon],
    ]
  }

  return null
}
