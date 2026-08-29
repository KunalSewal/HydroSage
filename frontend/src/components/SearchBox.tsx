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
    <div className="absolute left-1/2 top-4 z-[1000] w-96 -translate-x-1/2">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-md bg-slate-900/90 px-3 py-2 text-slate-100 shadow-lg backdrop-blur"
      >
        {status === 'searching' ? (
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        ) : (
          <Search className="h-4 w-4 text-slate-400" />
        )}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search a place..."
          className="w-full bg-transparent text-sm outline-none placeholder:text-slate-500"
        />
      </form>
      {results.length > 0 && (
        <ul className="mt-1 rounded-md bg-slate-900/95 text-sm text-slate-100 shadow-lg">
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
                className="block w-full px-3 py-2 text-left hover:bg-slate-800"
              >
                {result.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {status === 'no-results' && (
        <p className="mt-1 rounded-md bg-slate-900/95 px-3 py-2 text-sm text-slate-400 shadow-lg">
          No places found for "{query}".
        </p>
      )}
      {status === 'error' && (
        <p className="mt-1 rounded-md bg-red-950/90 px-3 py-2 text-sm text-red-200 shadow-lg">{errorMessage}</p>
      )}
    </div>
  )
}
