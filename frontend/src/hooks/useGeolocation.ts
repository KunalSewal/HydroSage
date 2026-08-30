import { useCallback, useEffect, useState } from 'react'

export const DEFAULT_CENTER = { lat: 21.19, lon: 81.3 } // Bhilai/Durg, Chhattisgarh

export type GeolocationStatus = 'locating' | 'located' | 'unavailable'

export interface GeolocationResult {
  position: { lat: number; lon: number }
  status: GeolocationStatus
  locate: () => void
  // Increments on every locate() completion, success or failure -- even
  // when the resulting position is byte-identical to the previous one
  // (the common case: your GPS fix hasn't moved between two clicks).
  // Consumers that recenter a map on `position` alone would otherwise see
  // no change to react to and silently do nothing on a second click.
  requestId: number
}

export function useGeolocation(): GeolocationResult {
  const [position, setPosition] = useState(DEFAULT_CENTER)
  const [status, setStatus] = useState<GeolocationStatus>('locating')
  const [requestId, setRequestId] = useState(0)

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setStatus('unavailable')
      setRequestId((id) => id + 1)
      return
    }
    setStatus('locating')
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ lat: result.coords.latitude, lon: result.coords.longitude })
        setStatus('located')
        setRequestId((id) => id + 1)
      },
      () => {
        setPosition(DEFAULT_CENTER)
        setStatus('unavailable')
        setRequestId((id) => id + 1)
      },
      // Without an explicit timeout, a denied-but-not-yet-answered browser
      // permission prompt (or a genuinely slow GPS fix) can leave the button
      // spinning indefinitely with no feedback -- bound it instead.
      { timeout: 10_000 },
    )
  }, [])

  useEffect(() => {
    queueMicrotask(() => locate())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { position, status, locate, requestId }
}
