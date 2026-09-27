import { Pentagon, RectangleHorizontal, Upload } from 'lucide-react'
import type { DrawShape } from './MapView'
import SearchBox from './SearchBox'

interface TopBarProps {
  onResultSelected: (lat: number, lon: number) => void
  onUploadClick: () => void
  onDrawClick: (shape: DrawShape) => void
}

const iconButton =
  'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-hs-amber hover:bg-hs-amber/15'

// Replaces the old permanent "Click a point / Upload contour map" tab
// toggle -- uploading a survey is a deliberate, occasional action, not a
// permanent second half of the screen, so it's folded in here as a
// secondary icon instead. Drawing a land area sits alongside it for the
// same reason.
export default function TopBar({ onResultSelected, onUploadClick, onDrawClick }: TopBarProps) {
  return (
    <div className="absolute left-1/2 top-4 z-[1000] flex w-full max-w-md -translate-x-1/2 items-center gap-2 rounded-full border border-hs-amber/15 bg-hs-panel/85 px-3 py-2 text-hs-cream shadow-lg backdrop-blur-md">
      <div className="flex-1">
        <SearchBox onResultSelected={onResultSelected} />
      </div>
      <div className="h-5 w-px shrink-0 bg-hs-cream/15" />
      <button
        type="button"
        onClick={() => onDrawClick('Polygon')}
        aria-label="Draw a land area"
        title="Draw a land area (click to add points, click the first point to finish)"
        className={iconButton}
      >
        <Pentagon className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => onDrawClick('Rectangle')}
        aria-label="Draw a rectangular land area"
        title="Draw a rectangular land area (click two opposite corners)"
        className={iconButton}
      >
        <RectangleHorizontal className="h-4 w-4" />
      </button>
      <button type="button" onClick={onUploadClick} aria-label="Upload a contour map" className={iconButton}>
        <Upload className="h-4 w-4" />
      </button>
    </div>
  )
}
