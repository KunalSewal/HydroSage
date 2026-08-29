import { useCallback, useRef, useState } from 'react'
import { createVillage, getElevation, getRecommendation, type ElevationData, type Recommendation, type Village } from '../api/client'

export type SiteStatus = 'idle' | 'locating' | 'located' | 'analyzing' | 'analyzed' | 'error'
export type RecommendationStatus = 'idle' | 'loading' | 'done' | 'error'

export interface SiteSelectionState {
  status: SiteStatus
  village: Village | null
  elevation: ElevationData | null
  errorMessage: string | null
  lastPoint: { lat: number; lon: number } | null
  // A separate sub-machine: recommendation is an optional enrichment of an
  // already-analyzed site (rainfall/runoff/pond sizing), not a replacement
  // for the contour/catchment view -- both can be visible at once.
  recommendationStatus: RecommendationStatus
  recommendation: Recommendation | null
  recommendationError: string | null
}

const initialState: SiteSelectionState = {
  status: 'idle',
  village: null,
  elevation: null,
  errorMessage: null,
  lastPoint: null,
  recommendationStatus: 'idle',
  recommendation: null,
  recommendationError: null,
}

export function useSiteSelection() {
  const [state, setState] = useState<SiteSelectionState>(initialState)
  // Shared across selectPoint/analyze/getRecommendation deliberately: any
  // newer action (a fresh click, a re-analyze) should invalidate an
  // in-flight recommendation fetch for the site it superseded, same as it
  // already invalidates an in-flight analyze() call.
  const requestId = useRef(0)

  const selectPoint = useCallback(async (lat: number, lon: number) => {
    const id = ++requestId.current
    setState((prev) => ({ ...prev, status: 'locating', errorMessage: null, lastPoint: { lat, lon } }))
    try {
      const village = await createVillage(lat, lon)
      if (id !== requestId.current) return // superseded by a newer call -- discard
      setState((prev) => ({
        ...prev,
        status: 'located',
        village,
        elevation: null,
        recommendationStatus: 'idle',
        recommendation: null,
        recommendationError: null,
      }))
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

  const getFullRecommendation = useCallback(() => {
    setState((prev) => {
      if (prev.status !== 'analyzed' || !prev.village) return prev
      const id = ++requestId.current
      const village = prev.village
      getRecommendation(village.id)
        .then((recommendation) => {
          if (id !== requestId.current) return
          setState((current) => ({ ...current, recommendationStatus: 'done', recommendation }))
        })
        .catch((error: unknown) => {
          if (id !== requestId.current) return
          setState((current) => ({
            ...current,
            recommendationStatus: 'error',
            recommendationError: error instanceof Error ? error.message : 'something went wrong',
          }))
        })
      return { ...prev, recommendationStatus: 'loading', recommendationError: null }
    })
  }, [])

  return { state, selectPoint, analyze, getFullRecommendation }
}
