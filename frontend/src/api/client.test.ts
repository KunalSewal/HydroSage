import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVillage, getElevation, listVillages, searchPlaces } from './client'

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
})
