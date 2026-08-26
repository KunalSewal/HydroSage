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
})
