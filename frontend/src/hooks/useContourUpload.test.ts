import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useContourUpload } from './useContourUpload'

vi.mock('../api/client')

const analysis = {
  pond_location: { lat: 21.24, lon: 81.29 },
  catchment_area_m2: 1_787_602,
  catchment_area_hectares: 178.76,
  catchment_cell_count: 1234,
  flow_accumulation_at_pond: 999,
  catchment_boundary: [[81.28, 21.24]] as [number, number][],
  source_bbox: { min_lon: 81.28, min_lat: 21.24, max_lon: 81.31, max_lat: 21.26 },
  grid_resolution: 300,
  min_elevation: 267,
  max_elevation: 298,
  contours: [],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useContourUpload', () => {
  beforeEach(() => {
    vi.mocked(client.analyzeContourFile).mockResolvedValue(analysis)
  })

  it('starts idle', () => {
    const { result } = renderHook(() => useContourUpload())
    expect(result.current.state.status).toBe('idle')
  })

  it('upload moves idle -> uploading -> analyzed with the result set', async () => {
    const { result } = renderHook(() => useContourUpload())
    const file = new File(['<kml/>'], 'contours.kml')

    act(() => {
      result.current.upload(file)
    })
    expect(result.current.state.status).toBe('uploading')
    expect(result.current.state.fileName).toBe('contours.kml')

    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))
    expect(result.current.state.result).toEqual(analysis)
  })

  it('upload failure moves to error with a message', async () => {
    vi.mocked(client.analyzeContourFile).mockRejectedValue(new Error('could not parse contour KML'))
    const { result } = renderHook(() => useContourUpload())

    await act(() => result.current.upload(new File(['bad'], 'bad.kml')))

    expect(result.current.state.status).toBe('error')
    expect(result.current.state.errorMessage).toBe('could not parse contour KML')
  })

  it('discards a stale upload result when a newer upload has already resolved', async () => {
    const first = deferred<typeof analysis>()
    const secondResult = { ...analysis, catchment_area_hectares: 42 }
    const second = deferred<typeof analysis>()
    vi.mocked(client.analyzeContourFile).mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)

    const { result } = renderHook(() => useContourUpload())

    act(() => {
      result.current.upload(new File(['a'], 'a.kml')) // resolves LAST
    })
    act(() => {
      result.current.upload(new File(['b'], 'b.kml')) // resolves FIRST
    })

    await act(async () => {
      second.resolve(secondResult)
      await second.promise
    })
    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))
    expect(result.current.state.result).toEqual(secondResult)

    await act(async () => {
      first.resolve(analysis)
      await first.promise
    })

    expect(result.current.state.result).toEqual(secondResult)
  })

  it('reset returns to idle', async () => {
    const { result } = renderHook(() => useContourUpload())
    await act(() => result.current.upload(new File(['a'], 'a.kml')))
    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))

    act(() => result.current.reset())

    expect(result.current.state.status).toBe('idle')
    expect(result.current.state.result).toBeNull()
  })
})
