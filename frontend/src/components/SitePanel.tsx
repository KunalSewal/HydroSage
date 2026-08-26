import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Loader2, MapPin, Mountain } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { SiteSelectionState } from '../hooks/useSiteSelection'

interface SitePanelProps {
  state: SiteSelectionState
  onAnalyze: () => void
  onRetry: () => void
}

// Counts up to each of `targets` over `durationMs` instead of snapping
// straight to the final numbers, per the spec's animation section. Takes an
// array so multiple related numbers (here: min/max elevation) animate off a
// single shared rAF loop and land in the same state update -- two separate
// loops each computing their own progress could settle on different frames
// a tick apart, which is invisible to the eye but flaky for tests that
// assert on both numbers being final at once.
//
// `start` is derived from the timestamp of the *first* rAF callback rather
// than a separately-captured `performance.now()`. In real browsers these two
// clocks are identical, but in jsdom (used by the test suite) the timestamp
// passed to requestAnimationFrame callbacks is not guaranteed to share an
// origin with the global `performance.now()` -- mixing them produced a large
// spurious offset that made the animation never converge within a test's
// waitFor timeout. Deriving `start` from the callback's own clock keeps both
// reads on the same timeline in every environment.
function useCountUp(targets: number[], durationMs = 600): number[] {
  const [values, setValues] = useState<number[]>(() => targets.map(() => 0))

  useEffect(() => {
    let frame: number
    let start: number | null = null
    function tick(now: number) {
      if (start === null) start = now
      const progress = Math.min((now - start) / durationMs, 1)
      setValues(targets.map((target) => Math.round(target * progress)))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
    // targets is a fresh array each render; spreading its values keeps the
    // effect keyed on the actual numbers rather than array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durationMs, ...targets])

  return values
}

export default function SitePanel({ state, onAnalyze, onRetry }: SitePanelProps) {
  const [minElevation, maxElevation] = useCountUp([
    state.elevation ? Math.round(state.elevation.min_elevation) : 0,
    state.elevation ? Math.round(state.elevation.max_elevation) : 0,
  ])

  return (
    <div className="flex h-full w-80 flex-col gap-4 bg-slate-900/90 p-6 text-slate-100 backdrop-blur">
      <h1 className="font-display text-xl font-semibold">HydroSage</h1>

      <AnimatePresence mode="wait">
        {state.status === 'idle' && (
          <motion.p
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-sm text-slate-400"
          >
            Click anywhere on the map to select a site, or search for a place above.
          </motion.p>
        )}

        {state.status === 'locating' && (
          <motion.div
            key="locating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 text-sm text-slate-300"
          >
            <Loader2 className="h-4 w-4 animate-spin" />
            Locating...
          </motion.div>
        )}

        {(state.status === 'located' || state.status === 'analyzing' || state.status === 'analyzed') &&
          state.village && (
            <motion.div
              key="located"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-3"
            >
              <div className="flex items-start gap-2">
                <MapPin className="mt-1 h-4 w-4 text-sky-400" />
                <div>
                  <p className="font-medium">{state.village.name}</p>
                  <p className="text-xs text-slate-400">
                    {state.village.district}, {state.village.state}
                  </p>
                </div>
              </div>

              {state.status === 'located' && (
                <button
                  type="button"
                  onClick={onAnalyze}
                  className="rounded-md bg-sky-500 px-3 py-2 text-sm font-medium text-white hover:bg-sky-400"
                >
                  Analyze this site
                </button>
              )}

              {state.status === 'analyzing' && (
                <div className="flex items-center gap-2 text-sm text-slate-300">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Fetching elevation...
                </div>
              )}

              {state.status === 'analyzed' && state.elevation && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 rounded-md bg-slate-800 p-3 text-sm"
                >
                  <Mountain className="h-4 w-4 text-emerald-400" />
                  <span>
                    Elevation {minElevation}m &ndash; {maxElevation}m
                  </span>
                </motion.div>
              )}
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
              <AlertTriangle className="h-4 w-4" />
              {state.errorMessage}
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
            >
              Retry
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
