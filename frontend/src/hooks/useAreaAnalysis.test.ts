import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useAreaAnalysis } from './useAreaAnalysis'

vi.mock('../api/client')

const square: [number, number][] = [
  [81.3, 21.2],
  [81.31, 21.2],
  [81.31, 21.21],
  [81.3, 21.21],
]

const analysis = {
  pond_location: { lat: 21.205, lon: 81.305 },
  catchment_area_m2: 49_000,
  catchment_area_hectares: 4.9,
  catchment_cell_count: 50,
  flow_accumulation_at_pond: 50,
  catchment_boundary: [[81.30, 21.20]] as [number, number][],
  source_bbox: { min_lon: 81.29, min_lat: 21.19, max_lon: 81.32, max_lat: 21.22 },
  grid_resolution: 86,
  min_elevation: 280,
  max_elevation: 300,
  contours: [],
  average_annual_rainfall_mm: 1344.6,
  rainfall_source: 'nasa-power',
  runoff_volume_m3: 16483,
  runoff_coefficient: 0.25,
  pond_options: [],
  available_land_hectares: null,
  selected_area: square,
  selected_area_hectares: 115,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('useAreaAnalysis', () => {
  beforeEach(() => {
    vi.mocked(client.analyzeArea).mockReset()
    vi.mocked(client.analyzeArea).mockResolvedValue(analysis)
  })

  it('starts idle with no area', () => {
    const { result } = renderHook(() => useAreaAnalysis())
    expect(result.current.state.status).toBe('idle')
    expect(result.current.state.area).toBeNull()
  })

  it('analyze moves to analyzing with the drawn area shown right away, then analyzed', async () => {
    const { result } = renderHook(() => useAreaAnalysis())

    act(() => {
      result.current.analyze(square)
    })
    expect(result.current.state.status).toBe('analyzing')
    expect(result.current.state.area).toEqual(square)

    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))
    expect(result.current.state.result).toEqual(analysis)
    expect(client.analyzeArea).toHaveBeenCalledWith(square)
  })

  it('surfaces the backend error message', async () => {
    vi.mocked(client.analyzeArea).mockRejectedValue(new Error('area is too small (0.2 ha): draw at least 1 ha'))
    const { result } = renderHook(() => useAreaAnalysis())

    act(() => {
      result.current.analyze(square)
    })

    await waitFor(() => expect(result.current.state.status).toBe('error'))
    expect(result.current.state.errorMessage).toContain('too small')
  })

  it('discards a stale result when a newer area was drawn first', async () => {
    const first = deferred<typeof analysis>()
    const second = deferred<typeof analysis>()
    vi.mocked(client.analyzeArea).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result } = renderHook(() => useAreaAnalysis())
    const newer: [number, number][] = square.map(([lon, lat]) => [lon + 0.1, lat])

    act(() => {
      result.current.analyze(square)
    })
    act(() => {
      result.current.analyze(newer)
    })
    await act(async () => {
      second.resolve({ ...analysis, selected_area: newer })
    })
    await act(async () => {
      first.resolve(analysis)
    })

    expect(result.current.state.area).toEqual(newer)
    expect(result.current.state.result?.selected_area).toEqual(newer)
  })

  it('reset returns to idle and ignores an in-flight analysis', async () => {
    const pending = deferred<typeof analysis>()
    vi.mocked(client.analyzeArea).mockReturnValueOnce(pending.promise)
    const { result } = renderHook(() => useAreaAnalysis())

    act(() => {
      result.current.analyze(square)
    })
    act(() => {
      result.current.reset()
    })
    await act(async () => {
      pending.resolve(analysis)
    })

    expect(result.current.state.status).toBe('idle')
    expect(result.current.state.result).toBeNull()
  })
})
