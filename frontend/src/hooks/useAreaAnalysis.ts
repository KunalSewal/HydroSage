import { useCallback, useRef, useState } from 'react'
import { analyzeArea, type AreaAnalysis } from '../api/client'

export type AreaAnalysisStatus = 'idle' | 'analyzing' | 'analyzed' | 'error'

export interface AreaAnalysisState {
  status: AreaAnalysisStatus
  // The drawn polygon, [lon, lat]. Set as soon as drawing finishes, so the
  // outline stays on the map while the analysis runs.
  area: [number, number][] | null
  result: AreaAnalysis | null
  errorMessage: string | null
}

const initialState: AreaAnalysisState = { status: 'idle', area: null, result: null, errorMessage: null }

export function useAreaAnalysis() {
  const [state, setState] = useState<AreaAnalysisState>(initialState)
  const requestId = useRef(0)

  const analyze = useCallback(async (area: [number, number][]) => {
    const id = ++requestId.current
    setState({ status: 'analyzing', area, result: null, errorMessage: null })
    try {
      const result = await analyzeArea(area)
      if (id !== requestId.current) return // superseded by a newer drawing -- discard
      setState({ status: 'analyzed', area, result, errorMessage: null })
    } catch (error) {
      if (id !== requestId.current) return
      setState({
        status: 'error',
        area,
        result: null,
        errorMessage: error instanceof Error ? error.message : 'something went wrong',
      })
    }
  }, [])

  const reset = useCallback(() => {
    requestId.current += 1 // discard any in-flight analysis
    setState(initialState)
  }, [])

  return { state, analyze, reset }
}
