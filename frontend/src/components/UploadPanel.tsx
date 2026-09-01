import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CloudRain, Droplets, Loader2, Ruler } from 'lucide-react'
import type { ContourUploadState } from '../hooks/useContourUpload'
import ContourLegend from './ContourLegend'

interface UploadPanelProps {
  state: ContourUploadState
  onRetry: () => void
}

export default function UploadPanel({ state, onRetry }: UploadPanelProps) {
  return (
    <AnimatePresence mode="wait">
      {state.status === 'uploading' && (
        <motion.div
          key="uploading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 text-sm text-hs-cream/80"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Analyzing {state.fileName}...
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
          <ContourLegend minElevation={state.result.min_elevation} maxElevation={state.result.max_elevation} />
          <div className="flex items-start gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
            <Droplets className="mt-0.5 h-4 w-4 text-hs-amber" />
            <div>
              <p className="font-medium">Recommended pond site</p>
              <p className="text-xs text-hs-muted">
                {state.result.pond_location.lat.toFixed(5)}, {state.result.pond_location.lon.toFixed(5)}
              </p>
              <p className="mt-1 text-xs text-hs-muted">
                Catchment area: {state.result.catchment_area_hectares.toFixed(1)} ha
              </p>
              <p className="text-xs text-hs-muted">
                Elevation: {Math.round(state.result.min_elevation)}m &ndash; {Math.round(state.result.max_elevation)}m
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
            <div className="flex items-center gap-2">
              <CloudRain className="h-4 w-4 text-hs-teal" />
              <span>
                {state.result.average_annual_rainfall_mm === null || state.result.runoff_volume_m3 === null ? (
                  <span className="text-hs-muted">Rainfall data unavailable &mdash; sizing by terrain capacity only</span>
                ) : (
                  <>
                    {Math.round(state.result.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                    {Math.round(state.result.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
                  </>
                )}
              </span>
            </div>
            <div className="flex items-start gap-2">
              <Ruler className="mt-0.5 h-4 w-4 text-hs-teal" />
              <div className="flex flex-col gap-1">
                <span className="text-xs text-hs-muted">Pond size options (limited by terrain capacity and annual runoff):</span>
                {state.result.pond_options.map((option) => (
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
            {state.result.available_land_hectares !== null && (
              <p className="text-xs text-hs-muted/70">
                ~{state.result.available_land_hectares.toFixed(1)} ha of land available nearby (excluding
                buildings, roads, and water bodies)
              </p>
            )}
          </div>
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
            Try another file
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
