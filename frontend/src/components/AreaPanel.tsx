import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Loader2, SquareDashed } from 'lucide-react'
import type { AreaAnalysisState } from '../hooks/useAreaAnalysis'
import AnalysisResult from './AnalysisResult'

interface AreaPanelProps {
  state: AreaAnalysisState
  onClear: () => void
}

export default function AreaPanel({ state, onClear }: AreaPanelProps) {
  return (
    <AnimatePresence mode="wait">
      {state.status === 'analyzing' && (
        <motion.div
          key="analyzing"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 text-sm text-hs-cream/80"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Analyzing the selected area: terrain, catchment, rainfall...
        </motion.div>
      )}

      {state.status === 'analyzed' && state.result && (
        <motion.div
          key="analyzed"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="flex flex-col gap-3"
        >
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2">
              <SquareDashed className="h-4 w-4 text-hs-amber" />
              Selected area: {state.result.selected_area_hectares.toFixed(1)} ha
            </span>
            <button
              type="button"
              onClick={onClear}
              className="rounded-md bg-hs-mid/60 px-2 py-1 text-xs font-medium hover:bg-hs-mid"
            >
              Clear
            </button>
          </div>
          <AnalysisResult result={state.result} />
        </motion.div>
      )}

      {state.status === 'error' && (
        <motion.div
          key="error"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex flex-col gap-2 rounded-md bg-red-950/60 p-3 text-sm text-red-200"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {state.errorMessage}
          </div>
          <button
            type="button"
            onClick={onClear}
            className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
          >
            Draw a different area
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
