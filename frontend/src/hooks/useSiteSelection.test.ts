import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useSiteSelection } from './useSiteSelection'

vi.mock('../api/client')

const village = { id: 'v1', name: 'Test Village', state: 'CG', district: 'Durg', lat: 21.19, lon: 81.3 }
const elevation = {
  village_id: 'v1',
  bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
  min_elevation: 250,
  max_elevation: 300,
  contours: [],
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
})
