import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Droplets, Loader2, UploadCloud } from 'lucide-react'
import { useRef } from 'react'
import type { ContourUploadState } from '../hooks/useContourUpload'

interface UploadPanelProps {
  state: ContourUploadState
  onUpload: (file: File) => void
  onReset: () => void
}

export default function UploadPanel({ state, onUpload, onReset }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) onUpload(file)
    event.target.value = '' // allow re-selecting the same file after a reset
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
            <button
              type="button"
              onClick={onReset}
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
