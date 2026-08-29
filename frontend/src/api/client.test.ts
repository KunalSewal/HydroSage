import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyzeContourFile, createVillage, getElevation, getRecommendation, listVillages, searchPlaces } from './client'

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listVillages returns parsed JSON on success', async () => {
    const villages = [{ id: '1', name: 'Test', state: 'MH', district: 'Test Dist', lat: 1, lon: 2 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(villages) }))

    const result = await listVillages()

    expect(result).toEqual(villages)
  })

  it('createVillage posts lat/lon and returns the created village', async () => {
    const village = { id: '2', name: 'New', state: 'CG', district: 'Durg', lat: 21.19, lon: 81.35 }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(village) })
    vi.stubGlobal('fetch', fetchMock)

    const result = await createVillage(21.19, 81.35)

    expect(result).toEqual(village)
    const [, options] = fetchMock.mock.calls[0]
    expect(JSON.parse(options.body)).toEqual({ lat: 21.19, lon: 81.35 })
  })

  it('getElevation throws a readable error on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'village not found' }) }))

    await expect(getElevation('missing-id')).rejects.toThrow('village not found')
  })

  it('extracts a readable message from a Pydantic validation error (detail is an array, not a string)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            detail: [{ loc: ['body', 'lat'], msg: 'Input should be a valid number', type: 'float_parsing' }],
          }),
      }),
    )

    await expect(getElevation('some-id')).rejects.toThrow('Input should be a valid number')
  })

  it('falls back to a status-based message when the response body is not JSON at all', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: () => Promise.reject(new SyntaxError('Unexpected token < in JSON')),
      }),
    )

    await expect(getElevation('some-id')).rejects.toThrow('502')
  })

  it('searchPlaces returns parsed results', async () => {
    const results = [{ display_name: 'Bhilai, Chhattisgarh', lat: 21.19, lon: 81.35 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(results) }))

    const result = await searchPlaces('Bhilai')

    expect(result).toEqual(results)
  })

  it('analyzeContourFile uploads the file as multipart form data and returns the analysis', async () => {
    const analysis = {
      pond_location: { lat: 21.24, lon: 81.29 },
      catchment_area_m2: 1_787_602,
      catchment_area_hectares: 178.76,
      catchment_cell_count: 1234,
      flow_accumulation_at_pond: 999,
      catchment_boundary: [[81.28, 21.24]],
      source_bbox: { min_lon: 81.28, min_lat: 21.24, max_lon: 81.31, max_lat: 21.26 },
      grid_resolution: 300,
      min_elevation: 267,
      max_elevation: 298,
      contours: [],
      average_annual_rainfall_mm: 1415.2,
      runoff_volume_m3: 175442.6,
      runoff_coefficient: 0.25,
      pond_options: [{ depth_m: 3, surface_area_m2: 58466, side_length_m: 241.8, fits_available_land: true }],
      available_land_hectares: 741.8,
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(analysis) })
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['<kml/>'], 'contours.kml', { type: 'application/vnd.google-earth.kml+xml' })

    const result = await analyzeContourFile(file)

    expect(result).toEqual(analysis)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/analyzeContour')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('file')).toBe(file)
  })

  it('analyzeContourFile throws a readable error on a non-OK response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, json: () => Promise.resolve({ detail: 'expected a .kml file' }) }),
    )
    const file = new File(['not kml'], 'notes.txt')

    await expect(analyzeContourFile(file)).rejects.toThrow('expected a .kml file')
  })

  it('getRecommendation posts to /villages/{id}/recommend and returns parsed JSON', async () => {
    const recommendation = {
      village_id: 'v1',
      catchment_area_hectares: 1.96,
      average_annual_rainfall_mm: 1436.4,
      runoff_volume_m3: 7043.4,
      runoff_coefficient: 0.25,
      pond_options: [{ depth_m: 3, surface_area_m2: 2347.8, side_length_m: 48.5, fits_available_land: true }],
      available_land_hectares: 1155.3,
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(recommendation) })
    vi.stubGlobal('fetch', fetchMock)

    const result = await getRecommendation('v1')

    expect(result).toEqual(recommendation)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/villages/v1/recommend')
    expect(options.method).toBe('POST')
  })

  it('getRecommendation throws a readable error on a non-OK response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'village not found' }) }),
    )

    await expect(getRecommendation('missing-id')).rejects.toThrow('village not found')
  })
})
