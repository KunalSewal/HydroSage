import MapView from './components/MapView'
import SearchBox from './components/SearchBox'
import SitePanel from './components/SitePanel'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'

function App() {
  const { position } = useGeolocation()
  const { state, selectPoint, analyze } = useSiteSelection()

  const markerPosition = state.village ? { lat: state.village.lat, lon: state.village.lon } : null
  const contours = state.elevation?.contours ?? []

  return (
    <div className="relative flex h-full w-full">
      <div className="relative flex-1">
        <MapView center={position} markerPosition={markerPosition} contours={contours} onMapClick={selectPoint} />
        <SearchBox onResultSelected={selectPoint} />
      </div>
      <SitePanel
        state={state}
        onAnalyze={analyze}
        onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
      />
    </div>
  )
}

export default App
