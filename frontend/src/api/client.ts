const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface Village {
  id: string
  name: string
  state: string
  district: string
  lat: number
  lon: number
}

export interface Contour {
  elevation: number
  coordinates: [number, number][] // [lon, lat] — GeoJSON order, NOT Leaflet order
}

export interface BoundingBox {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

// The result of the backend's catchment analysis (domain/catchment.py),
// shared by both input flows -- click-map and KML-upload -- so a single
// pond marker / catchment boundary UI can render either one.
export interface CatchmentFields {
  pond_location: { lat: number; lon: number }
  catchment_area_m2: number
  catchment_area_hectares: number
  catchment_cell_count: number
  flow_accumulation_at_pond: number
  catchment_boundary: [number, number][] // [lon, lat], closed ring
}

export interface ElevationData extends CatchmentFields {
  village_id: string
  bbox: BoundingBox
  min_elevation: number
  max_elevation: number
  contours: Contour[]
}

export interface GeocodeResult {
  display_name: string
  lat: number
  lon: number
}

export interface CatchmentAnalysis extends CatchmentFields {
  source_bbox: BoundingBox
  grid_resolution: number
  min_elevation: number
  max_elevation: number
  contours: Contour[]
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body.detail ?? `request failed with status ${response.status}`)
  }
  return body as T
}

export async function listVillages(): Promise<Village[]> {
  const response = await fetch(`${API_BASE}/villages`)
  return parseOrThrow<Village[]>(response)
}

export async function createVillage(lat: number, lon: number): Promise<Village> {
  const response = await fetch(`${API_BASE}/villages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon }),
  })
  return parseOrThrow<Village>(response)
}

export async function getElevation(villageId: string): Promise<ElevationData> {
  const response = await fetch(`${API_BASE}/villages/${villageId}/elevation`)
  return parseOrThrow<ElevationData>(response)
}

export async function searchPlaces(query: string): Promise<GeocodeResult[]> {
  const response = await fetch(`${API_BASE}/geocode?query=${encodeURIComponent(query)}`)
  return parseOrThrow<GeocodeResult[]>(response)
}

export async function analyzeContourFile(file: File): Promise<CatchmentAnalysis> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE}/analyzeContour`, { method: 'POST', body: formData })
  return parseOrThrow<CatchmentAnalysis>(response)
}
