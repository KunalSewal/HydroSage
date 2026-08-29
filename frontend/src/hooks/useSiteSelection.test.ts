import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useSiteSelection } from './useSiteSelection'

vi.mock('../api/client')

const village = { id: 'v1', name: 'Test Village', state: 'CG', district: 'Durg', lat: 21.19, lon: 81.3 }
const villageB = { id: 'v2', name: 'Second Village', state: 'CG', district: 'Durg', lat: 22.0, lon: 82.0 }
const elevation = {
  village_id: 'v1',
  bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
  min_elevation: 250,
  max_elevation: 300,
  contours: [],
  pond_location: { lat: 21.191, lon: 81.301 },
  catchment_area_m2: 500_000,
  catchment_area_hectares: 50,
  catchment_cell_count: 400,
  flow_accumulation_at_pond: 999,
  catchment_boundary: [[81.29, 21.18]] as [number, number][],
}

/** A promise you can resolve/reject from outside its executor, for controlling resolution order in tests. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useSiteSelection', () => {
  beforeEach(() => {
    vi.mocked(client.createVillage).mockResolvedValue(village)
    vi.mocked(client.getElevation).mockResolvedValue(elevation)
  })

  it('starts idle', () => {
    const { result } = renderHook(() => useSiteSelection())
    expect(result.current.state.status).toBe('idle')
  })

  it('selectPoint moves idle -> locating -> located with the village set', async () => {
    const { result } = renderHook(() => useSiteSelection())

    act(() => {
      result.current.selectPoint(21.19, 81.3)
    })
    expect(result.current.state.status).toBe('locating')

    await waitFor(() => expect(result.current.state.status).toBe('located'))
    expect(result.current.state.village).toEqual(village)
  })

  it('analyze moves located -> analyzing -> analyzed with elevation set', async () => {
    const { result } = renderHook(() => useSiteSelection())
    await act(() => result.current.selectPoint(21.19, 81.3))
    await waitFor(() => expect(result.current.state.status).toBe('located'))

    act(() => {
      result.current.analyze()
    })
    expect(result.current.state.status).toBe('analyzing')

    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))
    expect(result.current.state.elevation).toEqual(elevation)
  })

  it('selectPoint failure moves to error with a message, but keeps the attempted point', async () => {
    vi.mocked(client.createVillage).mockRejectedValue(new Error("couldn't identify a site here"))
    const { result } = renderHook(() => useSiteSelection())

    await act(() => result.current.selectPoint(0, 0))

    expect(result.current.state.status).toBe('error')
    expect(result.current.state.errorMessage).toBe("couldn't identify a site here")
    expect(result.current.state.lastPoint).toEqual({ lat: 0, lon: 0 })
  })

  it('analyze failure moves to error with a message', async () => {
    vi.mocked(client.getElevation).mockRejectedValue(new Error('elevation service unavailable'))
    const { result } = renderHook(() => useSiteSelection())
    await act(() => result.current.selectPoint(21.19, 81.3))
    await waitFor(() => expect(result.current.state.status).toBe('located'))

    await act(() => result.current.analyze())

    expect(result.current.state.status).toBe('error')
    expect(result.current.state.errorMessage).toBe('elevation service unavailable')
  })

  it('discards a stale selectPoint result when a newer selectPoint has already resolved', async () => {
    const first = deferred<typeof village>()
    const second = deferred<typeof villageB>()
    vi.mocked(client.createVillage).mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)

    const { result } = renderHook(() => useSiteSelection())

    // Fire selectPoint(A) then selectPoint(B) before either resolves.
    act(() => {
      result.current.selectPoint(21.19, 81.3) // A -- will resolve LAST
    })
    act(() => {
      result.current.selectPoint(22.0, 82.0) // B -- will resolve FIRST
    })

    // Resolve the newer call (B) first.
    await act(async () => {
      second.resolve(villageB)
      await second.promise
    })
    await waitFor(() => expect(result.current.state.status).toBe('located'))
    expect(result.current.state.village).toEqual(villageB)

    // Now resolve the stale call (A). A well-behaved hook discards this.
    await act(async () => {
      first.resolve(village)
      await first.promise
    })

    // State must still reflect B, not the stale A that resolved after it.
    expect(result.current.state.village).toEqual(villageB)
    expect(result.current.state.status).toBe('located')
    expect(result.current.state.lastPoint).toEqual({ lat: 22.0, lon: 82.0 })
  })

  it('discards a stale analyze result when a newer selectPoint has superseded it', async () => {
    const analysis = deferred<typeof elevation>()
    vi.mocked(client.getElevation).mockImplementationOnce(() => analysis.promise)

    const { result } = renderHook(() => useSiteSelection())
    await act(() => result.current.selectPoint(21.19, 81.3))
    await waitFor(() => expect(result.current.state.status).toBe('located'))

    // Kick off an analysis for village A, then supersede it with a brand-new selection
    // before the analysis resolves.
    act(() => {
      result.current.analyze()
    })
    expect(result.current.state.status).toBe('analyzing')

    vi.mocked(client.createVillage).mockResolvedValueOnce(villageB)
    await act(() => result.current.selectPoint(22.0, 82.0))
    await waitFor(() => expect(result.current.state.status).toBe('located'))
    expect(result.current.state.village).toEqual(villageB)

    // The stale analysis for village A now resolves. It must not clobber the
    // newer selection's state.
    await act(async () => {
      analysis.resolve(elevation)
      await analysis.promise
    })

    expect(result.current.state.status).toBe('located')
    expect(result.current.state.village).toEqual(villageB)
    expect(result.current.state.elevation).toBeNull()
  })
})
