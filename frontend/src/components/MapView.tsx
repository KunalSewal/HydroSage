import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Marker, Polygon, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { BoundingBox, Contour } from '../api/client'
import { contourColor } from '../lib/contourColor'

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

function RecenterOnChange({ position }: { position: { lat: number; lon: number } }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo([position.lat, position.lon], map.getZoom())
  }, [position.lat, position.lon, map])
  return null
}

// Used by the KML-upload flow: there's no GPS/click point to recenter on,
// so the map jumps to fit the uploaded contour map's actual coverage area.
function FitBounds({ bbox }: { bbox: BoundingBox }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(
      [
        [bbox.min_lat, bbox.min_lon],
        [bbox.max_lat, bbox.max_lon],
      ],
      { padding: [32, 32] },
    )
  }, [bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon, map])
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
}: MapViewProps) {
  return (
    <MapContainer center={[center.lat, center.lon]} zoom={12} className="h-full w-full">
      <TileLayer
        attribution="Tiles &copy; Esri"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      />
      <ClickHandler onMapClick={onMapClick} />
      {fitBoundsTo ? <FitBounds bbox={fitBoundsTo} /> : <RecenterOnChange position={markerPosition ?? center} />}
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
