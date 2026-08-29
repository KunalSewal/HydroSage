import { contourGradientCss } from '../lib/contourColor'

interface ContourLegendProps {
  minElevation: number
  maxElevation: number
}

export default function ContourLegend({ minElevation, maxElevation }: ContourLegendProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="h-2 w-full rounded-full" style={{ background: contourGradientCss() }} />
      <div className="flex justify-between text-xs text-slate-400">
        <span>{Math.round(minElevation)}m</span>
        <span>{Math.round(maxElevation)}m</span>
      </div>
    </div>
  )
}
