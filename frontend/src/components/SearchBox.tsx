import { Search } from 'lucide-react'
import { useState } from 'react'
import { searchPlaces } from '../api/client'

interface SearchBoxProps {
  onResultSelected: (lat: number, lon: number) => void
}

export default function SearchBox({ onResultSelected }: SearchBoxProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ display_name: string; lat: number; lon: number }[]>([])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    const found = await searchPlaces(query)
    setResults(found)
  }

  return (
    <div className="absolute left-1/2 top-4 z-[1000] w-96 -translate-x-1/2">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-md bg-slate-900/90 px-3 py-2 text-slate-100 shadow-lg backdrop-blur"
      >
        <Search className="h-4 w-4 text-slate-400" />
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
    </div>
  )
}
