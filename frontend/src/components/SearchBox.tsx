import { Loader2, Search } from 'lucide-react'
import { useState } from 'react'
import { searchPlaces } from '../api/client'

interface SearchBoxProps {
  onResultSelected: (lat: number, lon: number) => void
}

type Status = 'idle' | 'searching' | 'no-results' | 'error'

export default function SearchBox({ onResultSelected }: SearchBoxProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ display_name: string; lat: number; lon: number }[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setStatus('searching')
    setErrorMessage(null)
    try {
      const found = await searchPlaces(query)
      setResults(found)
      setStatus(found.length === 0 ? 'no-results' : 'idle')
    } catch (error) {
      setResults([])
      setStatus('error')
      setErrorMessage(error instanceof Error ? error.message : 'search failed')
    }
  }

  return (
    <div className="relative w-full">
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        {status === 'searching' ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-hs-muted" />
        ) : (
          <Search className="h-4 w-4 shrink-0 text-hs-muted" />
        )}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search a place..."
          className="w-full bg-transparent text-sm outline-none placeholder:text-hs-muted"
        />
      </form>
      {results.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-10 mt-2 rounded-md bg-hs-panel/95 text-sm text-hs-cream shadow-lg">
          {results.map((result) => (
            <li key={`${result.lat}-${result.lon}`}>
              <button
                type="button"
                onClick={() => {
                  onResultSelected(result.lat, result.lon)
                  setResults([])
                  setStatus('idle')
                  setQuery(result.display_name)
                }}
                className="block w-full px-3 py-2 text-left hover:bg-hs-mid/60"
              >
                {result.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {status === 'no-results' && (
        <p className="absolute left-0 right-0 top-full z-10 mt-2 rounded-md bg-hs-panel/95 px-3 py-2 text-sm text-hs-muted shadow-lg">
          No places found for "{query}".
        </p>
      )}
      {status === 'error' && (
        <p className="absolute left-0 right-0 top-full z-10 mt-2 rounded-md bg-red-950/90 px-3 py-2 text-sm text-red-200 shadow-lg">
          {errorMessage}
        </p>
      )}
    </div>
  )
}
