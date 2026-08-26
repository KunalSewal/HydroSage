import { useCallback, useEffect, useState } from 'react'

export const DEFAULT_CENTER = { lat: 21.19, lon: 81.3 } // Bhilai/Durg, Chhattisgarh

export type GeolocationStatus = 'locating' | 'located' | 'unavailable'

export interface GeolocationResult {
  position: { lat: number; lon: number }
  status: GeolocationStatus
  locate: () => void
}

export function useGeolocation(): GeolocationResult {
  const [position, setPosition] = useState(DEFAULT_CENTER)
  const [status, setStatus] = useState<GeolocationStatus>('locating')

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setStatus('unavailable')
      return
    }
    setStatus('locating')
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ lat: result.coords.latitude, lon: result.coords.longitude })
        setStatus('located')
      },
      () => {
        setPosition(DEFAULT_CENTER)
        setStatus('unavailable')
      },
    )
  }, [])

  useEffect(() => {
    queueMicrotask(() => locate())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { position, status, locate }
}
