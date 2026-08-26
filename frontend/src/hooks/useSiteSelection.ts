import { useCallback, useRef, useState } from 'react'
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
  const requestId = useRef(0)

  const selectPoint = useCallback(async (lat: number, lon: number) => {
    const id = ++requestId.current
    setState((prev) => ({ ...prev, status: 'locating', errorMessage: null, lastPoint: { lat, lon } }))
    try {
      const village = await createVillage(lat, lon)
      if (id !== requestId.current) return // superseded by a newer call -- discard
      setState((prev) => ({ ...prev, status: 'located', village, elevation: null }))
    } catch (error) {
      if (id !== requestId.current) return
      setState((prev) => ({
        ...prev,
        status: 'error',
        errorMessage: error instanceof Error ? error.message : 'something went wrong',
      }))
    }
  }, [])

  const analyze = useCallback(() => {
    setState((prev) => {
      if (prev.status !== 'located' || !prev.village) return prev
      const id = ++requestId.current
      const village = prev.village
      getElevation(village.id)
        .then((elevation) => {
          if (id !== requestId.current) return
          setState((current) => ({ ...current, status: 'analyzed', elevation }))
        })
        .catch((error: unknown) => {
          if (id !== requestId.current) return
          setState((current) => ({
            ...current,
            status: 'error',
            errorMessage: error instanceof Error ? error.message : 'something went wrong',
          }))
        })
      return { ...prev, status: 'analyzing', errorMessage: null }
    })
  }, [])

  return { state, selectPoint, analyze }
}
