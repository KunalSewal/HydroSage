import { LocateFixed, Loader2 } from 'lucide-react'
import type { GeolocationStatus } from '../hooks/useGeolocation'

interface LocateButtonProps {
  onClick: () => void
  status: GeolocationStatus
}

export default function LocateButton({ onClick, status }: LocateButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Locate me"
      aria-label="Locate me"
      className="absolute right-4 top-4 z-[1000] flex h-10 w-10 items-center justify-center rounded-full bg-hs-panel/85 text-hs-cream shadow-lg backdrop-blur-md hover:bg-hs-mid"
    >
      {status === 'locating' ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <LocateFixed className="h-4 w-4 text-hs-amber" />
      )}
    </button>
  )
}
