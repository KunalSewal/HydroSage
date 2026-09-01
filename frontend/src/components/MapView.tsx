import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Marker, Polygon, Polyline, TileLayer, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import type { BoundingBox, Contour } from '../api/client'
import { contourColor } from '../lib/contourColor'
import { resolveFocusBounds, type FocusBounds } from '../lib/mapFocus'

// A fresh element per distinct position (see the `key` on <Marker> below)
// is required for the CSS mount animation to replay on every new click —
// react-leaflet otherwise reuses the same DOM node and just moves it.
const markerIcon = L.divIcon({
  className: 'hydrosage-marker',
  html: '<div class="marker-bounce h-4 w-4 rounded-full bg-sky-400 ring-4 ring-sky-400/30"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

// A distinct color from the site-selection marker, so a recommended pond
// location (from the KML/catchment flow) doesn't read as "the point you clicked".
const pondMarkerIcon = L.divIcon({
  className: 'hydrosage-marker',
  html: '<div class="marker-bounce h-4 w-4 rounded-full bg-amber-400 ring-4 ring-amber-400/30"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

interface MapViewProps {
  center: { lat: number; lon: number }
  markerPosition: { lat: number; lon: number } | null
  contours: Contour[]
  onMapClick: (lat: number, lon: number) => void
  catchmentBoundary?: [number, number][] | null
  pondLocation?: { lat: number; lon: number } | null
  fitBoundsTo?: BoundingBox | null
  // Measured height of the results sheet overlaying the bottom of the map, so
  // a fitted catchment can be kept in the strip still visible above it.
  sheetHeight?: number
  // Bumped by useGeolocation on every locate() completion, even when the
  // resulting position is unchanged -- see RecenterOnChange below for why
  // this needs to be a separate signal from the position itself.
  geoRequestId?: number
}

function ClickHandler({ onMapClick }: { onMapClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(event) {
      onMapClick(event.latlng.lat, event.latlng.lng)
    },
  })
  return null
}

// Contours arrive as [lon, lat] (GeoJSON order); Leaflet wants [lat, lng].
// Revealed a few at a time on a short interval for a "drawing in" feel
// rather than every line snapping in at once. Colored by elevation (a
// hypsometric-style ramp) so the distinct bands the backend already
// computes are actually visible, instead of one flat line color.
function ContourLayer({ contours }: { contours: Contour[] }) {
  const [visibleCount, setVisibleCount] = useState(0)

  const [minElevation, maxElevation] = useMemo(() => {
    if (contours.length === 0) return [0, 0]
    const elevations = contours.map((c) => c.elevation)
    return [Math.min(...elevations), Math.max(...elevations)]
  }, [contours])

  useEffect(() => {
    setVisibleCount(0)
    if (contours.length === 0) return
    const step = Math.max(1, Math.ceil(contours.length / 20))
    const interval = setInterval(() => {
      setVisibleCount((count) => {
        const next = count + step
        if (next >= contours.length) clearInterval(interval)
        return Math.min(next, contours.length)
      })
    }, 40)
    return () => clearInterval(interval)
  }, [contours])

  return (
    <>
      {contours.slice(0, visibleCount).map((contour, index) => (
        <Polyline
          key={index}
          positions={contour.coordinates.map(([lon, lat]) => [lat, lon])}
          pathOptions={{
            color: contourColor(contour.elevation, minElevation, maxElevation),
            weight: 1.5,
            opacity: 0.85,
          }}
        />
      ))}
    </>
  )
}

// The catchment boundary traced by the D8 delineation (domain/catchment.py) —
// the area of land that drains toward the recommended pond site.
function CatchmentBoundaryLayer({ boundary }: { boundary: [number, number][] }) {
  if (boundary.length === 0) return null
  return (
    <Polygon
      positions={boundary.map(([lon, lat]) => [lat, lon])}
      pathOptions={{ color: '#38bdf8', weight: 2, fillColor: '#38bdf8', fillOpacity: 0.12 }}
    />
  )
}

// A useful "you can see individual streets/fields" zoom level -- flyTo used
// to be called with the map's *current* zoom, which just panned in place if
// the user had zoomed out (e.g. to see the whole country) without ever
// zooming back in, making "locate me" look like it did nothing.
const MIN_USEFUL_ZOOM = 14

// `nonce` (typically useGeolocation's requestId) is in the dependency array
// specifically so clicking "locate me" twice in a row still recenters the
// map even when the returned coordinates are byte-identical to last time
// (the common case) -- position.lat/lon alone wouldn't change, so the
// effect would silently no-op without it, making the button look broken.
function RecenterOnChange({ position, nonce }: { position: { lat: number; lon: number }; nonce?: number }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo([position.lat, position.lon], Math.max(map.getZoom(), MIN_USEFUL_ZOOM))
  }, [position.lat, position.lon, nonce, map])
  return null
}

// Clearance for the floating chrome that sits over the map, so a fitted
// catchment lands in the space actually visible rather than behind the
// search bar or the results sheet.
const TOP_CHROME_PADDING_PX = 80 // TopBar / logo / locate button
const SIDE_PADDING_PX = 28
const SHEET_GAP_PX = 20 // breathing room between the catchment and the sheet's top edge

// The sheet animates its height over 450ms and ResizeObserver reports every
// intermediate frame; re-fitting on each one would make the map fight the
// animation. Waiting for the height to settle yields a single, smooth fit.
const FIT_SETTLE_MS = 180

// A farm-pond catchment is only ~200m across, and fitting one edge-to-edge
// lands at street level with no surrounding landscape to place it in. Capping
// the zoom leaves it filling roughly half the visible strip, with context.
// Larger catchments fit below this and are unaffected.
const MAX_FIT_ZOOM = 17

// Frames whatever the analysis produced -- the traced catchment when there is
// one, otherwise the uploaded sheet's extent (see lib/mapFocus). The bottom
// padding tracks the results sheet's measured height so the catchment stays
// clear of it as it expands.
function FitFocusBounds({ bounds, sheetHeight }: { bounds: FocusBounds; sheetHeight: number }) {
  const map = useMap()
  const [south, west] = bounds[0]
  const [north, east] = bounds[1]

  useEffect(() => {
    const timer = setTimeout(() => {
      map.fitBounds(
        [
          [south, west],
          [north, east],
        ],
        {
          paddingTopLeft: [SIDE_PADDING_PX, TOP_CHROME_PADDING_PX],
          paddingBottomRight: [SIDE_PADDING_PX, sheetHeight + SHEET_GAP_PX],
          maxZoom: MAX_FIT_ZOOM,
          animate: true,
          duration: 0.6,
        },
      )
    }, FIT_SETTLE_MS)
    return () => clearTimeout(timer)
  }, [south, west, north, east, sheetHeight, map])

  return null
}

export default function MapView({
  center,
  markerPosition,
  contours,
  onMapClick,
  catchmentBoundary,
  pondLocation,
  fitBoundsTo,
  sheetHeight = 0,
  geoRequestId,
}: MapViewProps) {
  const focusBounds = resolveFocusBounds(catchmentBoundary, fitBoundsTo)

  return (
    // Leaflet's zoom control defaults to the top left, directly under the
    // HydroSage brand mark; moved to the top right where it stacks below the
    // locate button as a single control cluster (see index.css for the offset).
    <MapContainer center={[center.lat, center.lon]} zoom={12} zoomControl={false} className="h-full w-full">
      <TileLayer
        attribution="Tiles &copy; Esri"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      />
      <ZoomControl position="topright" />
      <ClickHandler onMapClick={onMapClick} />
      {focusBounds ? (
        <FitFocusBounds bounds={focusBounds} sheetHeight={sheetHeight} />
      ) : (
        <RecenterOnChange position={markerPosition ?? center} nonce={markerPosition ? undefined : geoRequestId} />
      )}
      {markerPosition && (
        <Marker
          key={`${markerPosition.lat}-${markerPosition.lon}`}
          position={[markerPosition.lat, markerPosition.lon]}
          icon={markerIcon}
        />
      )}
      {pondLocation && (
        <Marker
          key={`pond-${pondLocation.lat}-${pondLocation.lon}`}
          position={[pondLocation.lat, pondLocation.lon]}
          icon={pondMarkerIcon}
        />
      )}
      {catchmentBoundary && <CatchmentBoundaryLayer boundary={catchmentBoundary} />}
      <ContourLayer contours={contours} />
    </MapContainer>
  )
}
