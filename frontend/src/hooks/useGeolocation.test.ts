import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_CENTER, useGeolocation } from './useGeolocation'

describe('useGeolocation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts locating and resolves to the real position on success', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 19.0, longitude: 74.0 } } as GeolocationPosition)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())

    expect(result.current.status).toBe('locating')
    await waitFor(() => expect(result.current.status).toBe('located'))
    expect(result.current.position).toEqual({ lat: 19.0, lon: 74.0 })
  })

  it('falls back to the default center when permission is denied', async () => {
    const getCurrentPosition = vi.fn((_success: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 1, message: 'denied' } as GeolocationPositionError)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())

    await waitFor(() => expect(result.current.status).toBe('unavailable'))
    expect(result.current.position).toEqual(DEFAULT_CENTER)
  })

  it('falls back to the default center when geolocation is not supported', async () => {
    vi.stubGlobal('navigator', {})

    const { result } = renderHook(() => useGeolocation())

    await waitFor(() => expect(result.current.status).toBe('unavailable'))
    expect(result.current.position).toEqual(DEFAULT_CENTER)
  })

  it('locate() re-triggers the lookup', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 19.0, longitude: 74.0 } } as GeolocationPosition)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())
    await waitFor(() => expect(result.current.status).toBe('located'))

    act(() => result.current.locate())

    expect(getCurrentPosition).toHaveBeenCalledTimes(2)
  })

  it('requestId increments even when locate() resolves to the same position twice', async () => {
    // A map that recenters based on `position` alone would silently do
    // nothing on the second click here, since the coordinates never
    // change -- this is what made the locate-me button look broken.
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 19.0, longitude: 74.0 } } as GeolocationPosition)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())
    await waitFor(() => expect(result.current.status).toBe('located'))
    const firstRequestId = result.current.requestId
    const firstPosition = result.current.position

    await act(() => result.current.locate())

    expect(result.current.position).toEqual(firstPosition) // unchanged coordinates
    expect(result.current.requestId).toBeGreaterThan(firstRequestId) // but a distinguishable new request
  })
})
