import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { Contour } from '../api/client'

// A fresh element per distinct position (see the `key` on <Marker> below)
// is required for the CSS mount animation to replay on every new click —
// react-leaflet otherwise reuses the same DOM node and just moves it.
const markerIcon = L.divIcon({
  className: 'hydrosage-marker',
  html: '<div class="marker-bounce h-4 w-4 rounded-full bg-sky-400 ring-4 ring-sky-400/30"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

interface MapViewProps {
  center: { lat: number; lon: number }
  markerPosition: { lat: number; lon: number } | null
  contours: Contour[]
  onMapClick: (lat: number, lon: number) => void
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
// rather than every line snapping in at once.
function ContourLayer({ contours }: { contours: Contour[] }) {
  const [visibleCount, setVisibleCount] = useState(0)

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
          pathOptions={{ color: '#38bdf8', weight: 1.5, opacity: 0.8 }}
        />
      ))}
    </>
  )
}

function RecenterOnChange({ position }: { position: { lat: number; lon: number } }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo([position.lat, position.lon], map.getZoom())
  }, [position.lat, position.lon, map])
  return null
}

export default function MapView({ center, markerPosition, contours, onMapClick }: MapViewProps) {
  return (
    <MapContainer center={[center.lat, center.lon]} zoom={12} className="h-full w-full">
      <TileLayer
        attribution="Tiles &copy; Esri"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      />
      <ClickHandler onMapClick={onMapClick} />
      <RecenterOnChange position={markerPosition ?? center} />
      {markerPosition && (
        <Marker
          key={`${markerPosition.lat}-${markerPosition.lon}`}
          position={[markerPosition.lat, markerPosition.lon]}
          icon={markerIcon}
        />
      )}
      <ContourLayer contours={contours} />
    </MapContainer>
  )
}
