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
  // Mirrors `state` for synchronous reads inside analyze()/getFullRecommendation()
  // -- see the comment on those below for why this exists.
  const stateRef = useRef(state)
  stateRef.current = state

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

  // The network call is deliberately outside the setState updater (reading
  // current state via stateRef instead of a functional update) -- React
  // StrictMode double-invokes updater functions passed to setState in dev,
  // and this used to fire getElevation() from inside one, silently doubling
  // every OpenTopography call during development.
  const analyze = useCallback(() => {
    const current = stateRef.current
    if (current.status !== 'located' || !current.village) return
    const id = ++requestId.current
    const village = current.village

    setState((prev) => ({ ...prev, status: 'analyzing', errorMessage: null }))
    getElevation(village.id)
      .then((elevation) => {
        if (id !== requestId.current) return
        setState((prev) => ({ ...prev, status: 'analyzed', elevation }))
      })
      .catch((error: unknown) => {
        if (id !== requestId.current) return
        setState((prev) => ({
          ...prev,
          status: 'error',
          errorMessage: error instanceof Error ? error.message : 'something went wrong',
        }))
      })
  }, [])

  const getFullRecommendation = useCallback(() => {
    const current = stateRef.current
    if (current.status !== 'analyzed' || !current.village) return
    const id = ++requestId.current
    const village = current.village

    setState((prev) => ({ ...prev, recommendationStatus: 'loading', recommendationError: null }))
    getRecommendation(village.id)
      .then((recommendation) => {
        if (id !== requestId.current) return
        setState((prev) => ({ ...prev, recommendationStatus: 'done', recommendation }))
      })
      .catch((error: unknown) => {
        if (id !== requestId.current) return
        setState((prev) => ({
          ...prev,
          recommendationStatus: 'error',
          recommendationError: error instanceof Error ? error.message : 'something went wrong',
        }))
      })
  }, [])

  return { state, selectPoint, analyze, getFullRecommendation }
}
