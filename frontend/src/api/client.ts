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

export interface PondOption {
  depth_m: number
  surface_area_m2: number
  side_length_m: number
  fits_available_land: boolean | null
}

// Rainfall -> runoff -> pond sizing -> land-availability, shared by both
// flows that compute it (the click-map /recommend endpoint and the
// KML-upload /analyzeContour endpoint), same reasoning as CatchmentFields.
export interface RecommendationFields {
  // Null together when the rainfall service was unreachable. The catchment
  // analysis is computed from the survey alone and stays valid; only these
  // runoff-derived figures are lost. See backend docs/DECISIONS.md D-011.
  average_annual_rainfall_mm: number | null
  runoff_volume_m3: number | null
  runoff_coefficient: number | null
  pond_options: PondOption[]
  available_land_hectares: number | null
}

export interface CatchmentAnalysis extends CatchmentFields, RecommendationFields {
  source_bbox: BoundingBox
  grid_resolution: number
  min_elevation: number
  max_elevation: number
  contours: Contour[]
}

export interface Recommendation extends RecommendationFields {
  village_id: string
  catchment_area_hectares: number
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Not a JSON body at all -- a raw 502/504 from a proxy, an empty
    // response, etc. Fall through to the status-based message below
    // rather than surfacing a raw JSON.parse error to the user.
  }

  if (!response.ok) {
    throw new Error(extractErrorMessage(body) ?? `request failed with status ${response.status}`)
  }
  return body as T
}

// FastAPI's `detail` is a plain string for a hand-raised HTTPException, but
// a list of {msg, loc, type} objects for a Pydantic validation error (422)
// -- passing that array straight to `new Error()` used to render as the
// unhelpful literal "[object Object]" in the UI.
function extractErrorMessage(body: unknown): string | null {
  if (body === null || typeof body !== 'object' || !('detail' in body)) return null
  const detail = (body as { detail: unknown }).detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : null))
      .filter((msg): msg is string => msg !== null)
    if (messages.length > 0) return messages.join('; ')
  }

  return null
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
  // Field name fixed by the API contract (see backend analyze_contour.py).
  formData.append('contour_map', file)
  const response = await fetch(`${API_BASE}/analyzeContour`, { method: 'POST', body: formData })
  return parseOrThrow<CatchmentAnalysis>(response)
}

export async function getRecommendation(villageId: string): Promise<Recommendation> {
  const response = await fetch(`${API_BASE}/villages/${villageId}/recommend`, { method: 'POST' })
  return parseOrThrow<Recommendation>(response)
}
