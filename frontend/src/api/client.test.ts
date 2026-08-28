import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyzeContourFile, createVillage, getElevation, listVillages, searchPlaces } from './client'

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
})
