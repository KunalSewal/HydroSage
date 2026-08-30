import { useState } from 'react'
import LocateButton from './components/LocateButton'
import MapView from './components/MapView'
import SearchBox from './components/SearchBox'
import SitePanel from './components/SitePanel'
import UploadPanel from './components/UploadPanel'
import { useContourUpload } from './hooks/useContourUpload'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'

type Mode = 'click' | 'upload'

function App() {
  const [mode, setMode] = useState<Mode>('click')
  const { position, status: geoStatus, locate, requestId: geoRequestId } = useGeolocation()
  const { state, selectPoint, analyze, getFullRecommendation } = useSiteSelection()
  const { state: uploadState, upload, reset: resetUpload } = useContourUpload()

  const isUploadMode = mode === 'upload' && uploadState.result !== null

  // state.lastPoint is set synchronously on click, before the reverse-geocode
  // round-trip resolves -- deriving from state.village instead left a beat of
  // nothing happening after every click while that request was in flight.
  const markerPosition = !isUploadMode ? state.lastPoint : null
  const contours = isUploadMode ? (uploadState.result?.contours ?? []) : (state.elevation?.contours ?? [])
  const catchmentBoundary = isUploadMode
    ? (uploadState.result?.catchment_boundary ?? null)
    : (state.elevation?.catchment_boundary ?? null)
  const pondLocation = isUploadMode ? (uploadState.result?.pond_location ?? null) : (state.elevation?.pond_location ?? null)
  const fitBoundsTo = isUploadMode ? (uploadState.result?.source_bbox ?? null) : null

  return (
    <div className="relative flex h-full w-full">
      <div className="relative flex-1">
        <MapView
          center={position}
          markerPosition={markerPosition}
          contours={contours}
          onMapClick={mode === 'click' ? selectPoint : () => {}}
          catchmentBoundary={catchmentBoundary}
          pondLocation={pondLocation}
          fitBoundsTo={fitBoundsTo}
          geoRequestId={geoRequestId}
        />
        {mode === 'click' && <SearchBox onResultSelected={selectPoint} />}
        {mode === 'click' && <LocateButton onClick={locate} status={geoStatus} />}
      </div>

      <div className="flex h-full w-80 flex-col gap-4 bg-slate-900/90 p-6 text-slate-100 backdrop-blur">
        <h1 className="font-display text-xl font-semibold">HydroSage</h1>

        <div className="flex gap-1 rounded-md bg-slate-800 p-1 text-xs font-medium">
          <button
            type="button"
            onClick={() => setMode('click')}
            className={`flex-1 rounded px-2 py-1.5 ${mode === 'click' ? 'bg-sky-500 text-white' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Click a point
          </button>
          <button
            type="button"
            onClick={() => setMode('upload')}
            className={`flex-1 rounded px-2 py-1.5 ${mode === 'upload' ? 'bg-sky-500 text-white' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Upload contour map
          </button>
        </div>

        {mode === 'click' ? (
          <SitePanel
            state={state}
            onAnalyze={analyze}
            onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
            onGetRecommendation={getFullRecommendation}
          />
        ) : (
          <UploadPanel state={uploadState} onUpload={upload} onReset={resetUpload} />
        )}
      </div>
    </div>
  )
}

export default App
