import { CloudRain, Droplets, Ruler } from 'lucide-react'
import type { CatchmentAnalysis } from '../api/client'
import ContourLegend from './ContourLegend'

const RAINFALL_SOURCE_LABELS: Record<string, string> = {
  'open-meteo': 'Open-Meteo, 10-year daily record',
  'nasa-power': 'NASA POWER, 20-year climatology',
}

// The full result of one analysis -- pond site, catchment, rainfall, runoff
// volume and pond sizing. Shared by the KML-upload and drawn-area flows,
// which return the same fields.
export default function AnalysisResult({ result }: { result: CatchmentAnalysis }) {
  return (
    <>
      <ContourLegend minElevation={result.min_elevation} maxElevation={result.max_elevation} />
      <div className="flex items-start gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
        <Droplets className="mt-0.5 h-4 w-4 text-hs-amber" />
        <div>
          <p className="font-medium">Recommended pond site</p>
          <p className="text-xs text-hs-muted">
            {result.pond_location.lat.toFixed(5)}, {result.pond_location.lon.toFixed(5)}
          </p>
          <p className="mt-1 text-xs text-hs-muted">Catchment area: {result.catchment_area_hectares.toFixed(1)} ha</p>
          <p className="text-xs text-hs-muted">
            Elevation: {Math.round(result.min_elevation)}m &ndash; {Math.round(result.max_elevation)}m
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
        <div className="flex items-start gap-2">
          <CloudRain className="mt-0.5 h-4 w-4 text-hs-teal" />
          <span>
            {result.average_annual_rainfall_mm === null || result.runoff_volume_m3 === null ? (
              <span className="text-hs-muted">Rainfall data unavailable &mdash; sizing by terrain capacity only</span>
            ) : (
              <>
                {Math.round(result.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                {Math.round(result.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
                {result.rainfall_source && (
                  <span className="block text-xs text-hs-muted">
                    Rainfall: {RAINFALL_SOURCE_LABELS[result.rainfall_source] ?? result.rainfall_source}
                  </span>
                )}
              </>
            )}
          </span>
        </div>
        <div className="flex items-start gap-2">
          <Ruler className="mt-0.5 h-4 w-4 text-hs-teal" />
          <div className="flex flex-col gap-1">
            <span className="text-xs text-hs-muted">Pond size options (limited by terrain capacity and annual runoff):</span>
            {result.pond_options.map((option) => (
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
        {result.available_land_hectares !== null && (
          <p className="text-xs text-hs-muted/70">
            ~{result.available_land_hectares.toFixed(1)} ha of land available nearby (excluding buildings, roads, and
            water bodies)
          </p>
        )}
      </div>
    </>
  )
}
