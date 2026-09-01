import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CloudRain, Droplets, Loader2, MapPin, Mountain, Ruler } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { SiteSelectionState } from '../hooks/useSiteSelection'
import ContourLegend from './ContourLegend'

interface SitePanelProps {
  state: SiteSelectionState
  onAnalyze: () => void
  onRetry: () => void
  onGetRecommendation: () => void
}

// Counts up to each of `targets` over `durationMs` instead of snapping
// straight to the final numbers. Takes an array so multiple related
// numbers (here: min/max elevation) animate off a single shared rAF loop
// and land in the same state update -- two separate loops each computing
// their own progress could settle on different frames a tick apart, which
// is invisible to the eye but flaky for tests that assert on both numbers
// being final at once.
//
// `start` is derived from the timestamp of the *first* rAF callback
// rather than a separately-captured `performance.now()`. In real browsers
// these two clocks are identical, but in jsdom (used by the test suite)
// the timestamp passed to requestAnimationFrame callbacks is not
// guaranteed to share an origin with the global `performance.now()` --
// mixing them produced a large spurious offset that made the animation
// never converge within a test's waitFor timeout. Deriving `start` from
// the callback's own clock keeps both reads on the same timeline in
// every environment.
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

export default function SitePanel({ state, onAnalyze, onRetry, onGetRecommendation }: SitePanelProps) {
  const [minElevation, maxElevation] = useCountUp([
    state.elevation ? Math.round(state.elevation.min_elevation) : 0,
    state.elevation ? Math.round(state.elevation.max_elevation) : 0,
  ])

  return (
    <>
      <AnimatePresence mode="wait">
        {state.status === 'locating' && (
          <motion.div
            key="locating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 text-sm text-hs-cream/80"
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
                <MapPin className="mt-1 h-4 w-4 text-hs-teal" />
                <div>
                  <p className="font-medium">{state.village.name}</p>
                  <p className="text-xs text-hs-muted">
                    {state.village.district}, {state.village.state}
                  </p>
                </div>
              </div>

              {state.status === 'located' && (
                <button
                  type="button"
                  onClick={onAnalyze}
                  className="rounded-md bg-hs-amber px-3 py-2 text-sm font-medium text-hs-deep hover:brightness-110"
                >
                  Analyze this site
                </button>
              )}

              {state.status === 'analyzing' && (
                <div className="flex items-center gap-2 text-sm text-hs-cream/80">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analyzing terrain and catchment...
                </div>
              )}

              {state.status === 'analyzed' && state.elevation && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col gap-2"
                >
                  <div className="flex items-center gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
                    <Mountain className="h-4 w-4 text-hs-teal" />
                    <span>
                      Elevation <span data-testid="min-elevation">{minElevation}</span>m
                      &ndash; <span data-testid="max-elevation">{maxElevation}</span>m
                    </span>
                  </div>
                  <ContourLegend minElevation={state.elevation.min_elevation} maxElevation={state.elevation.max_elevation} />
                  <div className="flex items-start gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
                    <Droplets className="mt-0.5 h-4 w-4 text-hs-amber" />
                    <div>
                      <p className="font-medium">Recommended pond site</p>
                      <p className="text-xs text-hs-muted">
                        {state.elevation.pond_location.lat.toFixed(5)}, {state.elevation.pond_location.lon.toFixed(5)}
                      </p>
                      <p className="mt-1 text-xs text-hs-muted">
                        Catchment area: {state.elevation.catchment_area_hectares.toFixed(1)} ha
                      </p>
                    </div>
                  </div>

                  {state.recommendationStatus === 'idle' && (
                    <button
                      type="button"
                      onClick={onGetRecommendation}
                      className="rounded-md bg-hs-mid px-3 py-2 text-sm font-medium text-hs-cream hover:bg-hs-mid/70"
                    >
                      Get pond recommendation
                    </button>
                  )}

                  {state.recommendationStatus === 'loading' && (
                    <div className="flex items-center gap-2 text-sm text-hs-cream/80">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Fetching rainfall, runoff, and pond sizing...
                    </div>
                  )}

                  {state.recommendationStatus === 'error' && (
                    <p className="text-xs text-red-300">{state.recommendationError}</p>
                  )}

                  {state.recommendationStatus === 'done' && state.recommendation && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex flex-col gap-2 rounded-md bg-hs-mid/40 p-3 text-sm"
                    >
                      <div className="flex items-center gap-2">
                        <CloudRain className="h-4 w-4 text-hs-teal" />
                        <span>
                          {Math.round(state.recommendation.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                          {Math.round(state.recommendation.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Ruler className="mt-0.5 h-4 w-4 text-hs-teal" />
                        <div className="flex flex-col gap-1">
                          <span className="text-xs text-hs-muted">Pond size options (sized to terrain capacity):</span>
                          {state.recommendation.pond_options.map((option) => (
                            <div key={option.depth_m} className="flex items-center gap-1.5 text-xs">
                              <span className="font-medium text-hs-cream">
                                {option.depth_m}m deep &times; {Math.round(option.side_length_m)}m square
                              </span>
                              {option.fits_available_land === false && (
                                <span className="text-hs-amber">(exceeds available land nearby)</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                      {state.recommendation.available_land_hectares !== null && (
                        <p className="text-xs text-hs-muted/70">
                          ~{state.recommendation.available_land_hectares.toFixed(1)} ha of land available nearby
                          (excluding buildings, roads, and water bodies)
                        </p>
                      )}
                    </motion.div>
                  )}
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
    </>
  )
}
