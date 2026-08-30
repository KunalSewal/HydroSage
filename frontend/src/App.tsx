import { AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import BottomSheet from './components/BottomSheet'
import DropZoneOverlay from './components/DropZoneOverlay'
import IdleHint from './components/IdleHint'
import LoadingScreen from './components/LoadingScreen'
import LocateButton from './components/LocateButton'
import MapView from './components/MapView'
import SitePanel from './components/SitePanel'
import TopBar from './components/TopBar'
import UploadPanel from './components/UploadPanel'
import { useContourUpload } from './hooks/useContourUpload'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'

function App() {
  const { position, status: geoStatus, locate, requestId: geoRequestId } = useGeolocation()
  const { state, selectPoint, analyze, getFullRecommendation } = useSiteSelection()
  const { state: uploadState, upload, reset: resetUpload } = useContourUpload()
  const [isDropZoneOpen, setIsDropZoneOpen] = useState(false)

  // Once a file's been chosen and is uploading/analyzed/erroring, that
  // result takes over the map and bottom sheet -- entry is now via the
  // drop-zone overlay (Task 6) instead of a permanent tab, so this is
  // derived from upload state instead of a separately-tracked mode.
  const isUploadMode = uploadState.status !== 'idle'

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

  // requestId starts at 0 and only increments once useGeolocation's very
  // first locate() completes (success or failure) -- so this is precisely
  // "still waiting on the automatic on-load geolocation", not "any time
  // status happens to be 'locating'" (which would also be true for a later
  // manual re-locate via LocateButton, wrongly re-showing the loading
  // screen every time).
  const showLoadingScreen = geoRequestId === 0
  const showIdleHint = !isUploadMode && state.status === 'idle' && !isDropZoneOpen
  const showSiteSheet = !isUploadMode && state.status !== 'idle'
  const showUploadSheet = isUploadMode

  function handleFileChosen(file: File) {
    setIsDropZoneOpen(false)
    upload(file)
  }

  function handleUploadRetry() {
    resetUpload()
    setIsDropZoneOpen(true)
  }

  return (
    <div className="relative h-full w-full">
      <AnimatePresence>{showLoadingScreen && <LoadingScreen />}</AnimatePresence>

      <MapView
        center={position}
        markerPosition={markerPosition}
        contours={contours}
        onMapClick={!isUploadMode ? selectPoint : () => {}}
        catchmentBoundary={catchmentBoundary}
        pondLocation={pondLocation}
        fitBoundsTo={fitBoundsTo}
        geoRequestId={geoRequestId}
      />

      <div className="absolute left-4 top-4 z-[1000] rounded-full bg-hs-panel/70 px-3 py-1.5 font-display text-sm font-semibold text-hs-cream backdrop-blur-md">
        HydroSage
      </div>

      <TopBar onResultSelected={selectPoint} onUploadClick={() => setIsDropZoneOpen(true)} />
      <LocateButton onClick={locate} status={geoStatus} />

      {showIdleHint && <IdleHint />}

      {showSiteSheet && (
        <BottomSheet expandable={state.status === 'analyzed'}>
          <SitePanel
            state={state}
            onAnalyze={analyze}
            onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
            onGetRecommendation={getFullRecommendation}
          />
        </BottomSheet>
      )}

      {showUploadSheet && (
        <BottomSheet expandable={uploadState.status === 'analyzed'}>
          <UploadPanel state={uploadState} onRetry={handleUploadRetry} />
        </BottomSheet>
      )}

      <DropZoneOverlay
        isOpen={isDropZoneOpen}
        onClose={() => setIsDropZoneOpen(false)}
        onFileChosen={handleFileChosen}
      />
    </div>
  )
}

export default App
