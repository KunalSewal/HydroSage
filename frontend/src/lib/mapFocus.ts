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
// A drawn area is framed together with the catchment: the user needs to see
// the area they selected with the answer inside it, and a catchment can
// reach beyond the drawn area uphill, so neither alone contains the other.
//
// Kept apart from MapView so the decision is testable without standing up
// Leaflet in jsdom.
export function resolveFocusBounds(
  catchmentBoundary: [number, number][] | null | undefined,
  sourceBbox: BoundingBox | null | undefined,
  selectedArea?: [number, number][] | null,
): FocusBounds | null {
  if (catchmentBoundary && catchmentBoundary.length > 0) {
    // Rings arrive as [lon, lat] (GeoJSON order); Leaflet wants [lat, lng].
    const points = selectedArea ? [...catchmentBoundary, ...selectedArea] : catchmentBoundary
    const lons = points.map(([lon]) => lon)
    const lats = points.map(([, lat]) => lat)
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
