import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CloudRain, Droplets, Loader2, Ruler, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
import type { ContourUploadState } from '../hooks/useContourUpload'
import ContourLegend from './ContourLegend'

interface UploadPanelProps {
  state: ContourUploadState
  onUpload: (file: File) => void
  onReset: () => void
}

export default function UploadPanel({ state, onUpload, onReset }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  // /analyzeContour already returns the full recommendation in one call
  // (no separate fetch to stage, unlike the click-map flow), but the
  // reveal is still staged behind a click for a consistent interaction
  // between both flows -- purely a display gate, not a second request.
  const [showRecommendation, setShowRecommendation] = useState(false)

  function handleFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) {
      setShowRecommendation(false)
      onUpload(file)
    }
    event.target.value = '' // allow re-selecting the same file after a reset
  }

  function handleReset() {
    setShowRecommendation(false)
    onReset()
  }

  return (
    <div className="flex flex-col gap-3">
      <input ref={inputRef} type="file" accept=".kml" className="hidden" onChange={handleFileChosen} />

      <AnimatePresence mode="wait">
        {state.status === 'idle' && (
          <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <p className="mb-3 text-sm text-slate-400">
              Or upload a contour map (KML) to identify a pond site and its catchment directly from surveyed data.
            </p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-slate-600 px-3 py-3 text-sm font-medium text-slate-300 hover:border-sky-400 hover:text-sky-300"
            >
              <UploadCloud className="h-4 w-4" />
              Upload contour map (.kml)
            </button>
          </motion.div>
        )}

        {state.status === 'uploading' && (
          <motion.div
            key="uploading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 text-sm text-slate-300"
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
            <div className="flex items-start gap-2 rounded-md bg-slate-800 p-3 text-sm">
              <Droplets className="mt-0.5 h-4 w-4 text-amber-400" />
              <div>
                <p className="font-medium">Recommended pond site</p>
                <p className="text-xs text-slate-400">
                  {state.result.pond_location.lat.toFixed(5)}, {state.result.pond_location.lon.toFixed(5)}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Catchment area: {state.result.catchment_area_hectares.toFixed(1)} ha
                </p>
                <p className="text-xs text-slate-400">
                  Elevation: {Math.round(state.result.min_elevation)}m &ndash; {Math.round(state.result.max_elevation)}m
                </p>
              </div>
            </div>

            {!showRecommendation && (
              <button
                type="button"
                onClick={() => setShowRecommendation(true)}
                className="rounded-md bg-sky-500 px-3 py-2 text-sm font-medium text-white hover:bg-sky-400"
              >
                Get pond recommendation
              </button>
            )}

            {showRecommendation && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col gap-2 rounded-md bg-slate-800 p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <CloudRain className="h-4 w-4 text-sky-400" />
                  <span>
                    {Math.round(state.result.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                    {Math.round(state.result.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <Ruler className="mt-0.5 h-4 w-4 text-emerald-400" />
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Pond size options (storage = annual runoff):</span>
                    {state.result.pond_options.map((option) => (
                      <div key={option.depth_m} className="flex items-center gap-1.5 text-xs">
                        <span className="font-medium text-slate-200">
                          {option.depth_m}m deep &times; {Math.round(option.side_length_m)}m square
                        </span>
                        {option.fits_available_land === false && (
                          <span className="text-amber-400">(exceeds available land nearby)</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                {state.result.available_land_hectares !== null && (
                  <p className="text-xs text-slate-500">
                    ~{state.result.available_land_hectares.toFixed(1)} ha of land available nearby (excluding
                    buildings, roads, and water bodies)
                  </p>
                )}
              </motion.div>
            )}

            <button
              type="button"
              onClick={handleReset}
              className="self-start rounded-md bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
            >
              Upload a different file
            </button>
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
              onClick={() => inputRef.current?.click()}
              className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
            >
              Try another file
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
