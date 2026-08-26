import { useCallback, useState } from 'react'
import { createVillage, getElevation, type ElevationData, type Village } from '../api/client'

export type SiteStatus = 'idle' | 'locating' | 'located' | 'analyzing' | 'analyzed' | 'error'

export interface SiteSelectionState {
  status: SiteStatus
  village: Village | null
  elevation: ElevationData | null
  errorMessage: string | null
  lastPoint: { lat: number; lon: number } | null
}

const initialState: SiteSelectionState = {
  status: 'idle',
  village: null,
  elevation: null,
  errorMessage: null,
  lastPoint: null,
}

export function useSiteSelection() {
  const [state, setState] = useState<SiteSelectionState>(initialState)

  const selectPoint = useCallback(async (lat: number, lon: number) => {
    setState((prev) => ({ ...prev, status: 'locating', errorMessage: null, lastPoint: { lat, lon } }))
    try {
      const village = await createVillage(lat, lon)
      setState((prev) => ({ ...prev, status: 'located', village, elevation: null }))
    } catch (error) {
      setState((prev) => ({
        ...prev,
        status: 'error',
        errorMessage: error instanceof Error ? error.message : 'something went wrong',
      }))
    }
  }, [])

  const analyze = useCallback(async () => {
    setState((prev) => {
      if (!prev.village) return prev
      return { ...prev, status: 'analyzing', errorMessage: null }
    })
    setState((current) => {
      if (current.status !== 'analyzing' || !current.village) return current
      getElevation(current.village.id)
        .then((elevation) => {
          setState((prev) => ({ ...prev, status: 'analyzed', elevation }))
        })
        .catch((error: unknown) => {
          setState((prev) => ({
            ...prev,
            status: 'error',
            errorMessage: error instanceof Error ? error.message : 'something went wrong',
          }))
        })
      return current
    })
  }, [])

  return { state, selectPoint, analyze }
}
