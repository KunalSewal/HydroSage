import { AnimatePresence } from 'framer-motion'
import { useCallback, useState } from 'react'
import AreaPanel from './components/AreaPanel'
import BottomSheet from './components/BottomSheet'
import DropZoneOverlay from './components/DropZoneOverlay'
import IdleHint from './components/IdleHint'
import LoadingScreen from './components/LoadingScreen'
import LocateButton from './components/LocateButton'
import MapView, { type DrawRequest, type DrawShape } from './components/MapView'
import SitePanel from './components/SitePanel'
import TopBar from './components/TopBar'
import UploadPanel from './components/UploadPanel'
import { useAreaAnalysis } from './hooks/useAreaAnalysis'
import { useContourUpload } from './hooks/useContourUpload'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'
import { pondLabel } from './lib/mapLabels'
import { squareAround } from './lib/squareArea'

// Set at build time for deployments without the database the village-based
// click flow needs (the four lab containers, docs/DEPLOYMENT.md): a click
// or a search result then analyzes a square around that point instead.
const CLICK_ANALYZES_AREA = import.meta.env.VITE_CLICK_ANALYZES_AREA === 'true'

function App() {
  const { position, status: geoStatus, locate, requestId: geoRequestId } = useGeolocation()
  const { state, selectPoint, analyze, getFullRecommendation } = useSiteSelection()
  const { state: uploadState, upload, reset: resetUpload } = useContourUpload()
  const { state: areaState, analyze: analyzeArea, reset: resetArea } = useAreaAnalysis()
  const [isDropZoneOpen, setIsDropZoneOpen] = useState(false)
  const [drawRequest, setDrawRequest] = useState<DrawRequest | null>(null)
  // Measured by whichever BottomSheet is mounted, so the map can fit the
  // catchment into the strip left visible above it. setState is passed
  // directly because its identity is stable -- an inline arrow here would
  // re-run the sheet's measuring effect on every render.
  const [sheetHeight, setSheetHeight] = useState(0)

  // Once a file's been chosen and is uploading/analyzed/erroring, that
  // result takes over the map and bottom sheet -- entry is now via the
  // drop-zone overlay (Task 6) instead of a permanent tab, so this is
  // derived from upload state instead of a separately-tracked mode.
  const isUploadMode = uploadState.status !== 'idle'
  // A drawn area takes over the same way an upload does. The two are
  // mutually exclusive: starting one resets the other (see handlers below).
  const isAreaMode = !isUploadMode && areaState.status !== 'idle'
  const fileOrAreaResult = isUploadMode ? uploadState.result : isAreaMode ? areaState.result : null

  // state.lastPoint is set synchronously on click, before the reverse-geocode
  // round-trip resolves -- deriving from state.village instead left a beat of
  // nothing happening after every click while that request was in flight.
  const isClickMode = !isUploadMode && !isAreaMode
  const markerPosition = isClickMode ? state.lastPoint : null
  const contours = isClickMode ? (state.elevation?.contours ?? []) : (fileOrAreaResult?.contours ?? [])
  const catchmentBoundary = isClickMode
    ? (state.elevation?.catchment_boundary ?? null)
    : (fileOrAreaResult?.catchment_boundary ?? null)
  const pondLocation = isClickMode ? (state.elevation?.pond_location ?? null) : (fileOrAreaResult?.pond_location ?? null)
  const fitBoundsTo = isClickMode ? null : (fileOrAreaResult?.source_bbox ?? null)
  // The click-map flow only knows the water volume after its second,
  // optional "Get pond recommendation" stage.
  const runoffVolume = isClickMode ? state.recommendation?.runoff_volume_m3 : fileOrAreaResult?.runoff_volume_m3
  const catchmentHectares = isClickMode
    ? state.elevation?.catchment_area_hectares
    : fileOrAreaResult?.catchment_area_hectares
  const selectedArea = isAreaMode ? areaState.area : null

  // requestId starts at 0 and only increments once useGeolocation's very
  // first locate() completes (success or failure) -- so this is precisely
  // "still waiting on the automatic on-load geolocation", not "any time
  // status happens to be 'locating'" (which would also be true for a later
  // manual re-locate via LocateButton, wrongly re-showing the loading
  // screen every time).
  const showLoadingScreen = geoRequestId === 0
  const showIdleHint = isClickMode && state.status === 'idle' && !isDropZoneOpen && drawRequest === null
  const showSiteSheet = isClickMode && state.status !== 'idle'
  const showUploadSheet = isUploadMode
  const showAreaSheet = isAreaMode

  function handleFileChosen(file: File) {
    setIsDropZoneOpen(false)
    resetArea()
    upload(file)
  }

  function handlePointChosen(lat: number, lon: number) {
    if (CLICK_ANALYZES_AREA) {
      resetUpload()
      analyzeArea(squareAround(lat, lon))
      return
    }
    resetArea()
    selectPoint(lat, lon)
  }

  function handleDrawClick(shape: DrawShape) {
    setDrawRequest((previous) => ({ shape, nonce: (previous?.nonce ?? 0) + 1 }))
  }

  // Stable identity, so MapView's draw controller subscribes once.
  const handleAreaDrawn = useCallback(
    (ring: [number, number][]) => {
      setDrawRequest(null)
      resetUpload()
      analyzeArea(ring)
    },
    [analyzeArea, resetUpload],
  )

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
        onMapClick={isClickMode || (isAreaMode && CLICK_ANALYZES_AREA) ? handlePointChosen : () => {}}
        catchmentBoundary={catchmentBoundary}
        pondLocation={pondLocation}
        fitBoundsTo={fitBoundsTo}
        sheetHeight={sheetHeight}
        geoRequestId={geoRequestId}
        drawRequest={drawRequest}
        onAreaDrawn={handleAreaDrawn}
        selectedArea={selectedArea}
        pondLabel={pondLocation ? pondLabel(runoffVolume, catchmentHectares) : null}
      />

      <div className="absolute left-4 top-4 z-[1000] rounded-full bg-hs-panel/70 px-3 py-1.5 font-display text-sm font-semibold text-hs-cream backdrop-blur-md">
        HydroSage
      </div>

      <TopBar
        onResultSelected={handlePointChosen}
        onUploadClick={() => setIsDropZoneOpen(true)}
        onDrawClick={handleDrawClick}
      />
      <LocateButton onClick={locate} status={geoStatus} />

      {showIdleHint && <IdleHint />}

      {showSiteSheet && (
        <BottomSheet expandable={state.status === 'analyzed'} onHeightChange={setSheetHeight}>
          <SitePanel
            state={state}
            onAnalyze={analyze}
            onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
            onGetRecommendation={getFullRecommendation}
          />
        </BottomSheet>
      )}

      {showUploadSheet && (
        <BottomSheet expandable={uploadState.status === 'analyzed'} onHeightChange={setSheetHeight}>
          <UploadPanel state={uploadState} onRetry={handleUploadRetry} />
        </BottomSheet>
      )}

      {showAreaSheet && (
        <BottomSheet expandable={areaState.status === 'analyzed'} onHeightChange={setSheetHeight}>
          <AreaPanel state={areaState} onClear={resetArea} />
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
