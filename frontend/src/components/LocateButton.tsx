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
      className="absolute right-4 top-4 z-[1000] flex h-10 w-10 items-center justify-center rounded-md bg-slate-900/90 text-slate-100 shadow-lg backdrop-blur hover:bg-slate-800"
    >
      {status === 'locating' ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <LocateFixed className="h-4 w-4" />
      )}
    </button>
  )
}
