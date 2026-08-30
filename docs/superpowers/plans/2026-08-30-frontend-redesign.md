# HydroSage Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace HydroSage's fixed map+sidebar layout and default Tailwind styling with a full-bleed map, an "Earth & Water" visual design system, an animated loading screen, and a Google-Maps-style bottom sheet for results — all approved live via the visual-companion tool across 4 rounds.

**Architecture:** Presentation-layer only. Every existing hook (`useSiteSelection`, `useContourUpload`, `useGeolocation`) and `MapView`'s core map/marker/contour/boundary rendering logic is reused unchanged. New components (`LoadingScreen`, `IdleHint`, `TopBar`, `DropZoneOverlay`, `BottomSheet`) provide the new chrome; `SitePanel`/`UploadPanel` keep rendering the same state-driven content they always have, restyled and simplified now that `BottomSheet` owns the peek/expand mechanic instead of ad-hoc per-panel toggles.

**Tech Stack:** React 19 + TypeScript, Vite, Tailwind CSS v4 (CSS-first `@theme`), Framer Motion, `lucide-react`, `react-leaflet`, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-30-frontend-redesign-design.md`

## Global Constraints

- **No backend/API changes.** Every task in this plan touches only `frontend/src/` (plus `frontend/index.html`).
- **No changes to `useSiteSelection.ts`, `useContourUpload.ts`, `useGeolocation.ts`, or `MapView.tsx`'s map/marker/contour/boundary rendering.** Only `App.tsx`'s composition of `MapView`'s props changes (Task 11).
- **Color tokens:** `hs-deep` `#0a231d`, `hs-mid` `#173d33`, `hs-panel` `#0f2b24`, `hs-amber` `#f5c26b`, `hs-teal` `#5fc9ba`, `hs-cream` `#fdf6ec`, `hs-muted` `#a8d8ce` — defined once in Task 1, used via Tailwind utilities (`bg-hs-panel/90`, `text-hs-cream`, etc.) everywhere after.
- **Typography:** `--font-display: "Fraunces", "Georgia", serif` (headings/wordmark), `--font-sans: "Inter", system-ui, sans-serif` (body, already loaded — unchanged).
- **Animation:** use Framer Motion (`motion.*`, `AnimatePresence`) for all component-level animation, matching the rest of this codebase — no new global CSS `@keyframes` needed for this plan (the one pre-existing keyframe, `marker-bounce-in` in `index.css`, stays as-is; it's a special case for a Leaflet `divIcon`, which renders outside React's tree).
- **Every new component gets its own Vitest + Testing Library test file**, following this codebase's established conventions (`userEvent` for interaction, `screen.getBy*`/`findBy*` for assertions, not snapshot tests).
- **Run `npx tsc --noEmit`, `npx vitest run`, and `npm run build` after every task** — all three must be clean before moving on.
- **Commit after every task**, and verify the redesigned flow live in a real browser (Playwright) as the final task before considering this plan done — matching this project's established verification discipline all session.

---

### Task 1: Design tokens and fonts

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: Tailwind utility classes `bg-hs-deep`, `bg-hs-mid`, `bg-hs-panel`, `bg-hs-amber`, `bg-hs-teal`, `text-hs-cream`, `text-hs-muted` (and the `text-`/`border-`/etc. variants Tailwind v4 auto-generates from any `--color-*` token), plus `font-display` now resolving to Fraunces. All later tasks consume these.

- [ ] **Step 1: Add Fraunces to the Google Fonts link**

In `frontend/index.html`, replace the existing fonts `<link>`:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet" />
```

with:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Fraunces:wght@500;600;700&display=swap" rel="stylesheet" />
```

(Space Grotesk is dropped — it was the old default-display font, superseded by Fraunces per the approved design.)

- [ ] **Step 2: Update the theme tokens in `index.css`**

Replace the full contents of `frontend/src/index.css` with:

```css
@import "tailwindcss";

@theme {
  --font-display: "Fraunces", "Georgia", serif;
  --font-sans: "Inter", system-ui, sans-serif;

  --color-hs-deep: #0a231d;
  --color-hs-mid: #173d33;
  --color-hs-panel: #0f2b24;
  --color-hs-amber: #f5c26b;
  --color-hs-teal: #5fc9ba;
  --color-hs-cream: #fdf6ec;
  --color-hs-muted: #a8d8ce;
}

html, body, #root {
  height: 100%;
  margin: 0;
}

body {
  font-family: var(--font-sans);
  background-color: var(--color-hs-deep);
  color: var(--color-hs-cream);
}

@keyframes marker-bounce-in {
  0% { transform: scale(0) translateY(-20px); opacity: 0; }
  60% { transform: scale(1.2) translateY(0); opacity: 1; }
  100% { transform: scale(1) translateY(0); }
}
.marker-bounce {
  animation: marker-bounce-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

- [ ] **Step 3: Verify the build picks up the new tokens**

Run: `cd frontend && npm run build`
Expected: builds clean (no CSS errors — an unrecognized `--color-*` name would still build fine syntactically, so this step is really about catching typos in the CSS itself, not the tokens' correctness. Token correctness gets verified visually in Task 11's live check).

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/src/index.css
git commit -m "Add Earth & Water color tokens and Fraunces display font"
```

---

### Task 2: `LoadingScreen` component

**Files:**
- Create: `frontend/src/components/LoadingScreen.tsx`
- Test: `frontend/src/components/LoadingScreen.test.tsx`

**Interfaces:**
- Consumes: nothing (no props) — pure presentational, mounted/unmounted by `App.tsx` (Task 11) via `AnimatePresence`.
- Produces: `export default function LoadingScreen(): JSX.Element`, rendering a `data-testid="loading-screen"` root element.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/LoadingScreen.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LoadingScreen from './LoadingScreen'

describe('LoadingScreen', () => {
  it('shows the HydroSage wordmark', () => {
    render(<LoadingScreen />)
    expect(screen.getByTestId('loading-screen')).toBeInTheDocument()
    expect(screen.getByText('HydroSage')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/LoadingScreen.test.tsx`
Expected: FAIL — `Failed to resolve import "./LoadingScreen"`

- [ ] **Step 3: Implement `LoadingScreen`**

Create `frontend/src/components/LoadingScreen.tsx`:

```tsx
import { motion } from 'framer-motion'

// A terrain scan resolving into the app's own name -- the same visual
// language ContourLayer uses for real data (colored lines drawing in),
// just as the very first thing a user sees. Approved live via the
// visual-companion tool (docs/superpowers/specs/2026-08-30-frontend-redesign-design.md).
const CONTOUR_PATHS = [
  { d: 'M-20,260 C60,220 100,270 180,240 C260,210 300,250 420,220', delay: 0.1, duration: 2.4, color: '#5fc9ba' },
  { d: 'M-20,210 C60,170 100,220 180,190 C260,160 300,200 420,170', delay: 0.4, duration: 2.6, color: '#f5c26b' },
  { d: 'M-20,160 C60,120 100,170 180,140 C260,110 300,150 420,120', delay: 0.7, duration: 2.8, color: '#5fc9ba' },
  { d: 'M-20,110 C60,70 100,120 180,90 C260,60 300,100 420,70', delay: 1.0, duration: 3.0, color: '#f5c26b' },
]

export default function LoadingScreen() {
  return (
    <motion.div
      data-testid="loading-screen"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-gradient-to-br from-hs-mid to-hs-deep"
    >
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 320" preserveAspectRatio="none">
        {CONTOUR_PATHS.map((path, index) => (
          <motion.path
            key={index}
            d={path.d}
            fill="none"
            stroke={path.color}
            strokeWidth={1.2}
            strokeLinecap="round"
            opacity={0.4}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: path.duration, delay: path.delay, ease: 'easeOut' }}
          />
        ))}
      </svg>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1, delay: 0.3 }}
        className="relative text-center"
      >
        <h1 className="font-display text-3xl font-semibold text-hs-cream">HydroSage</h1>
        <p className="mt-2 text-xs tracking-wide text-hs-muted">Charting terrain&hellip;</p>
      </motion.div>
    </motion.div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/LoadingScreen.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LoadingScreen.tsx frontend/src/components/LoadingScreen.test.tsx
git commit -m "Add LoadingScreen: animated contour-line intro"
```

---

### Task 3: `IdleHint` component

**Files:**
- Create: `frontend/src/components/IdleHint.tsx`
- Test: `frontend/src/components/IdleHint.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: `export default function IdleHint(): JSX.Element` — a `pointer-events-none` overlay so it never blocks map clicks underneath it.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/IdleHint.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import IdleHint from './IdleHint'

describe('IdleHint', () => {
  it('shows the click-to-begin hint text', () => {
    render(<IdleHint />)
    expect(screen.getByText(/click anywhere to find a pond site/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/IdleHint.test.tsx`
Expected: FAIL — `Failed to resolve import "./IdleHint"`

- [ ] **Step 3: Implement `IdleHint`**

Create `frontend/src/components/IdleHint.tsx`:

```tsx
import { motion } from 'framer-motion'

// Fixes the "big empty map" complaint the redesign started from: a
// continuously-pulsing dot at the map's center so an unselected map never
// looks dead. pointer-events-none so it never intercepts the map click
// underneath it.
export default function IdleHint() {
  return (
    <div className="pointer-events-none absolute left-1/2 top-1/2 z-[900] -translate-x-1/2 -translate-y-1/2 text-center">
      <motion.div
        animate={{ opacity: [0.6, 1, 0.6], scale: [1, 1.25, 1] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        className="mx-auto mb-3 h-3.5 w-3.5 rounded-full bg-hs-amber"
      />
      <p className="text-xs font-medium text-hs-cream/90">Click anywhere to find a pond site</p>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/IdleHint.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/IdleHint.tsx frontend/src/components/IdleHint.test.tsx
git commit -m "Add IdleHint: pulsing click-to-begin indicator"
```

---

### Task 4: Refactor `SearchBox` to be composable

**Files:**
- Modify: `frontend/src/components/SearchBox.tsx`

**Interfaces:**
- Consumes: unchanged — `{ onResultSelected: (lat: number, lon: number) => void }`.
- Produces: unchanged public behavior; only the outermost wrapper changes from a viewport-positioned `absolute` pill to a `relative w-full` fragment, so `TopBar` (Task 5) can host it inside its own pill instead of `SearchBox` owning page-level positioning.

- [ ] **Step 1: Confirm the existing test file needs no changes**

Read `frontend/src/components/SearchBox.test.tsx` — it queries by `getByPlaceholderText`, `getByRole`, `findByText`, never by the wrapper's position/background classes. No edits needed here; Step 4 re-runs it to confirm.

- [ ] **Step 2: Replace `SearchBox.tsx`'s returned JSX**

Replace the full contents of `frontend/src/components/SearchBox.tsx` with:

```tsx
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
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Run the existing SearchBox tests to confirm they still pass unchanged**

Run: `cd frontend && npx vitest run src/components/SearchBox.test.tsx`
Expected: PASS (all 4 existing tests, no test file changes needed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SearchBox.tsx
git commit -m "Make SearchBox composable: drop its own page-level positioning"
```

---

### Task 5: `TopBar` component

**Files:**
- Create: `frontend/src/components/TopBar.tsx`
- Test: `frontend/src/components/TopBar.test.tsx`

**Interfaces:**
- Consumes: `SearchBox` (Task 4) with its existing `{ onResultSelected }` prop.
- Produces: `export default function TopBar(props: { onResultSelected: (lat: number, lon: number) => void; onUploadClick: () => void }): JSX.Element`. `App.tsx` (Task 11) mounts one `TopBar`, replacing the old `SearchBox` + tab-toggle chrome.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/TopBar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import TopBar from './TopBar'

describe('TopBar', () => {
  it('renders the search input', () => {
    render(<TopBar onResultSelected={vi.fn()} onUploadClick={vi.fn()} />)
    expect(screen.getByPlaceholderText(/search a place/i)).toBeInTheDocument()
  })

  it('calls onUploadClick when the upload icon is clicked', async () => {
    const onUploadClick = vi.fn()
    render(<TopBar onResultSelected={vi.fn()} onUploadClick={onUploadClick} />)

    await userEvent.click(screen.getByRole('button', { name: /upload a contour map/i }))

    expect(onUploadClick).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/TopBar.test.tsx`
Expected: FAIL — `Failed to resolve import "./TopBar"`

- [ ] **Step 3: Implement `TopBar`**

Create `frontend/src/components/TopBar.tsx`:

```tsx
import { Upload } from 'lucide-react'
import SearchBox from './SearchBox'

interface TopBarProps {
  onResultSelected: (lat: number, lon: number) => void
  onUploadClick: () => void
}

// Replaces the old permanent "Click a point / Upload contour map" tab
// toggle -- uploading a survey is a deliberate, occasional action, not a
// permanent second half of the screen, so it's folded in here as a
// secondary icon instead.
export default function TopBar({ onResultSelected, onUploadClick }: TopBarProps) {
  return (
    <div className="absolute left-1/2 top-4 z-[1000] flex w-full max-w-md -translate-x-1/2 items-center gap-2 rounded-full border border-hs-amber/15 bg-hs-panel/85 px-3 py-2 text-hs-cream shadow-lg backdrop-blur-md">
      <div className="flex-1">
        <SearchBox onResultSelected={onResultSelected} />
      </div>
      <div className="h-5 w-px shrink-0 bg-hs-cream/15" />
      <button
        type="button"
        onClick={onUploadClick}
        aria-label="Upload a contour map"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-hs-amber hover:bg-hs-amber/15"
      >
        <Upload className="h-4 w-4" />
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/TopBar.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TopBar.tsx frontend/src/components/TopBar.test.tsx
git commit -m "Add TopBar: search + upload icon, replaces the old tab toggle"
```

---

### Task 6: `DropZoneOverlay` component

**Files:**
- Create: `frontend/src/components/DropZoneOverlay.tsx`
- Test: `frontend/src/components/DropZoneOverlay.test.tsx`

**Interfaces:**
- Consumes: nothing external.
- Produces: `export default function DropZoneOverlay(props: { isOpen: boolean; onClose: () => void; onFileChosen: (file: File) => void }): JSX.Element`. `App.tsx` (Task 11) owns the `isOpen` state and wires `onFileChosen` to `useContourUpload`'s `upload`.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/DropZoneOverlay.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import DropZoneOverlay from './DropZoneOverlay'

describe('DropZoneOverlay', () => {
  it('renders nothing when closed', () => {
    render(<DropZoneOverlay isOpen={false} onClose={vi.fn()} onFileChosen={vi.fn()} />)
    expect(screen.queryByText(/drop your contour map/i)).not.toBeInTheDocument()
  })

  it('shows the drop zone when open', () => {
    render(<DropZoneOverlay isOpen onClose={vi.fn()} onFileChosen={vi.fn()} />)
    expect(screen.getByText(/drop your contour map/i)).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    render(<DropZoneOverlay isOpen onClose={onClose} onFileChosen={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /close upload/i }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onFileChosen when a file is chosen via the hidden input', async () => {
    const onFileChosen = vi.fn()
    render(<DropZoneOverlay isOpen onClose={vi.fn()} onFileChosen={onFileChosen} />)
    const file = new File(['<kml/>'], 'contours.kml')
    const input = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(input, file)

    expect(onFileChosen).toHaveBeenCalledWith(file)
  })

  it('calls onFileChosen when a file is dropped onto the surface', () => {
    const onFileChosen = vi.fn()
    render(<DropZoneOverlay isOpen onClose={vi.fn()} onFileChosen={onFileChosen} />)
    const file = new File(['<kml/>'], 'contours.kml')
    const surface = screen.getByTestId('dropzone-surface')

    fireEvent.drop(surface, { dataTransfer: { files: [file] } })

    expect(onFileChosen).toHaveBeenCalledWith(file)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/DropZoneOverlay.test.tsx`
Expected: FAIL — `Failed to resolve import "./DropZoneOverlay"`

- [ ] **Step 3: Implement `DropZoneOverlay`**

Create `frontend/src/components/DropZoneOverlay.tsx`:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { Map, X } from 'lucide-react'
import { useRef, useState } from 'react'

interface DropZoneOverlayProps {
  isOpen: boolean
  onClose: () => void
  onFileChosen: (file: File) => void
}

export default function DropZoneOverlay({ isOpen, onClose, onFileChosen }: DropZoneOverlayProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDraggingOver, setIsDraggingOver] = useState(false)

  function handleFile(file: File | undefined) {
    if (file) onFileChosen(file)
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          data-testid="dropzone-surface"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 z-[1500] flex items-center justify-center bg-hs-deep/85 backdrop-blur-sm"
          onDragOver={(event) => {
            event.preventDefault()
            setIsDraggingOver(true)
          }}
          onDragLeave={() => setIsDraggingOver(false)}
          onDrop={(event) => {
            event.preventDefault()
            setIsDraggingOver(false)
            handleFile(event.dataTransfer.files[0])
          }}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label="Close upload"
            className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full bg-hs-cream/10 text-hs-cream hover:bg-hs-cream/20"
          >
            <X className="h-4 w-4" />
          </button>
          <div
            onClick={() => inputRef.current?.click()}
            className={`cursor-pointer rounded-2xl border-2 border-dashed px-12 py-9 text-center transition-colors ${
              isDraggingOver ? 'border-hs-amber bg-hs-amber/10' : 'border-hs-amber/50'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".kml"
              className="hidden"
              onChange={(event) => handleFile(event.target.files?.[0])}
            />
            <Map className="mx-auto mb-3 h-7 w-7 text-hs-amber" />
            <h3 className="font-display text-lg font-semibold text-hs-cream">Drop your contour map here</h3>
            <p className="mt-1 text-xs text-hs-muted">or click to browse — accepts .kml files</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/DropZoneOverlay.test.tsx`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DropZoneOverlay.tsx frontend/src/components/DropZoneOverlay.test.tsx
git commit -m "Add DropZoneOverlay: drag-and-drop + click-to-browse KML upload"
```

---

### Task 7: `BottomSheet` component

**Files:**
- Create: `frontend/src/components/BottomSheet.tsx`
- Test: `frontend/src/components/BottomSheet.test.tsx`

**Interfaces:**
- Consumes: nothing external.
- Produces: `export default function BottomSheet(props: { expandable?: boolean; children: ReactNode }): JSX.Element`. `App.tsx` (Task 11) wraps `SitePanel`/`UploadPanel` in this instead of the old fixed sidebar `<div>`.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/BottomSheet.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import BottomSheet from './BottomSheet'

describe('BottomSheet', () => {
  it('renders children directly with no toggle when not expandable', () => {
    render(
      <BottomSheet>
        <p>Hello</p>
      </BottomSheet>,
    )
    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.queryByTestId('bottom-sheet-toggle')).not.toBeInTheDocument()
  })

  it('shows a toggle button when expandable, and flips its label on click', async () => {
    render(
      <BottomSheet expandable>
        <p>Details</p>
      </BottomSheet>,
    )
    const toggle = screen.getByTestId('bottom-sheet-toggle')
    expect(toggle).toHaveAttribute('aria-label', 'Expand details')

    await userEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-label', 'Collapse details')
  })

  it('keeps children mounted regardless of expanded state (visual clipping only, not conditional rendering)', async () => {
    render(
      <BottomSheet expandable>
        <p data-testid="content">Full content</p>
      </BottomSheet>,
    )
    expect(screen.getByTestId('content')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('bottom-sheet-toggle'))

    expect(screen.getByTestId('content')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/BottomSheet.test.tsx`
Expected: FAIL — `Failed to resolve import "./BottomSheet"`

- [ ] **Step 3: Implement `BottomSheet`**

Create `frontend/src/components/BottomSheet.tsx`:

```tsx
import { motion } from 'framer-motion'
import { ChevronUp } from 'lucide-react'
import { useState, type ReactNode } from 'react'

interface BottomSheetProps {
  expandable?: boolean
  children: ReactNode
}

const PEEK_MAX_HEIGHT = 100
const EXPANDED_MAX_HEIGHT = 520
const UNCLIPPED_MAX_HEIGHT = 2000 // effectively "no limit" -- framer-motion animates maxHeight more reliably between two numbers than between a number and 'none'

// A Google-Maps-style peek/expand results panel, replacing the old fixed
// sidebar. `expandable` is only true once there's real content worth
// hiding (the click-map flow's post-"analyzed" state, or the KML-upload
// flow's post-"analyzed" state) -- earlier, shorter states (e.g. "Locating...")
// render at full, unclipped height with no toggle at all.
export default function BottomSheet({ expandable = false, children }: BottomSheetProps) {
  const [expanded, setExpanded] = useState(false)
  const maxHeight = expandable ? (expanded ? EXPANDED_MAX_HEIGHT : PEEK_MAX_HEIGHT) : UNCLIPPED_MAX_HEIGHT

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0, maxHeight }}
      transition={{
        maxHeight: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
        opacity: { duration: 0.3 },
        y: { duration: 0.3 },
      }}
      className="absolute bottom-3 left-3 right-3 z-[1000] overflow-y-auto rounded-2xl border border-hs-amber/20 bg-hs-panel/90 px-4 py-3 text-hs-cream shadow-2xl backdrop-blur-md"
    >
      {expandable && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? 'Collapse details' : 'Expand details'}
          data-testid="bottom-sheet-toggle"
          className="absolute right-3 top-3 rounded-full p-1 text-hs-amber hover:bg-hs-amber/10"
        >
          <ChevronUp className={`h-4 w-4 transition-transform duration-300 ${expanded ? '' : 'rotate-180'}`} />
        </button>
      )}
      {children}
    </motion.div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/BottomSheet.test.tsx`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BottomSheet.tsx frontend/src/components/BottomSheet.test.tsx
git commit -m "Add BottomSheet: Google-Maps-style peek/expand results panel"
```

---

### Task 8: Restyle `SitePanel`, drop its now-redundant idle state

**Files:**
- Modify: `frontend/src/components/SitePanel.tsx`
- Modify: `frontend/src/components/SitePanel.test.tsx`

**Interfaces:**
- Consumes: unchanged — `SiteSelectionState`, `onAnalyze`, `onRetry`, `onGetRecommendation`.
- Produces: unchanged prop signature. `App.tsx` (Task 11) only ever mounts `SitePanel` when `state.status !== 'idle'` (the new `IdleHint` from Task 3 covers that case instead), so `SitePanel`'s own `'idle'` branch is now unreachable and is removed rather than left as dead code.

- [ ] **Step 1: Replace `SitePanel.tsx`**

Replace the full contents of `frontend/src/components/SitePanel.tsx` with:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CloudRain, Droplets, Loader2, MapPin, Mountain, Ruler } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { SiteSelectionState } from '../hooks/useSiteSelection'
import ContourLegend from './ContourLegend'

interface SitePanelProps {
  state: SiteSelectionState
  onAnalyze: () => void
  onRetry: () => void
  onGetRecommendation: () => void
}

// Counts up to each of `targets` over `durationMs` instead of snapping
// straight to the final numbers. Takes an array so multiple related
// numbers (here: min/max elevation) animate off a single shared rAF loop
// and land in the same state update -- two separate loops each computing
// their own progress could settle on different frames a tick apart, which
// is invisible to the eye but flaky for tests that assert on both numbers
// being final at once.
//
// `start` is derived from the timestamp of the *first* rAF callback
// rather than a separately-captured `performance.now()`. In real browsers
// these two clocks are identical, but in jsdom (used by the test suite)
// the timestamp passed to requestAnimationFrame callbacks is not
// guaranteed to share an origin with the global `performance.now()` --
// mixing them produced a large spurious offset that made the animation
// never converge within a test's waitFor timeout. Deriving `start` from
// the callback's own clock keeps both reads on the same timeline in
// every environment.
function useCountUp(targets: number[], durationMs = 600): number[] {
  const [values, setValues] = useState<number[]>(() => targets.map(() => 0))

  useEffect(() => {
    let frame: number
    let start: number | null = null
    function tick(now: number) {
      if (start === null) start = now
      const progress = Math.min((now - start) / durationMs, 1)
      setValues(targets.map((target) => Math.round(target * progress)))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
    // targets is a fresh array each render; spreading its values keeps the
    // effect keyed on the actual numbers rather than array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durationMs, ...targets])

  return values
}

export default function SitePanel({ state, onAnalyze, onRetry, onGetRecommendation }: SitePanelProps) {
  const [minElevation, maxElevation] = useCountUp([
    state.elevation ? Math.round(state.elevation.min_elevation) : 0,
    state.elevation ? Math.round(state.elevation.max_elevation) : 0,
  ])

  return (
    <>
      <AnimatePresence mode="wait">
        {state.status === 'locating' && (
          <motion.div
            key="locating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 text-sm text-hs-cream/80"
          >
            <Loader2 className="h-4 w-4 animate-spin" />
            Locating...
          </motion.div>
        )}

        {(state.status === 'located' || state.status === 'analyzing' || state.status === 'analyzed') &&
          state.village && (
            <motion.div
              key="located"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-3"
            >
              <div className="flex items-start gap-2">
                <MapPin className="mt-1 h-4 w-4 text-hs-teal" />
                <div>
                  <p className="font-medium">{state.village.name}</p>
                  <p className="text-xs text-hs-muted">
                    {state.village.district}, {state.village.state}
                  </p>
                </div>
              </div>

              {state.status === 'located' && (
                <button
                  type="button"
                  onClick={onAnalyze}
                  className="rounded-md bg-hs-amber px-3 py-2 text-sm font-medium text-hs-deep hover:brightness-110"
                >
                  Analyze this site
                </button>
              )}

              {state.status === 'analyzing' && (
                <div className="flex items-center gap-2 text-sm text-hs-cream/80">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analyzing terrain and catchment...
                </div>
              )}

              {state.status === 'analyzed' && state.elevation && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col gap-2"
                >
                  <div className="flex items-center gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
                    <Mountain className="h-4 w-4 text-hs-teal" />
                    <span>
                      Elevation <span data-testid="min-elevation">{minElevation}</span>m
                      &ndash; <span data-testid="max-elevation">{maxElevation}</span>m
                    </span>
                  </div>
                  <ContourLegend minElevation={state.elevation.min_elevation} maxElevation={state.elevation.max_elevation} />
                  <div className="flex items-start gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
                    <Droplets className="mt-0.5 h-4 w-4 text-hs-amber" />
                    <div>
                      <p className="font-medium">Recommended pond site</p>
                      <p className="text-xs text-hs-muted">
                        {state.elevation.pond_location.lat.toFixed(5)}, {state.elevation.pond_location.lon.toFixed(5)}
                      </p>
                      <p className="mt-1 text-xs text-hs-muted">
                        Catchment area: {state.elevation.catchment_area_hectares.toFixed(1)} ha
                      </p>
                    </div>
                  </div>

                  {state.recommendationStatus === 'idle' && (
                    <button
                      type="button"
                      onClick={onGetRecommendation}
                      className="rounded-md bg-hs-mid px-3 py-2 text-sm font-medium text-hs-cream hover:bg-hs-mid/70"
                    >
                      Get pond recommendation
                    </button>
                  )}

                  {state.recommendationStatus === 'loading' && (
                    <div className="flex items-center gap-2 text-sm text-hs-cream/80">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Fetching rainfall, runoff, and pond sizing...
                    </div>
                  )}

                  {state.recommendationStatus === 'error' && (
                    <p className="text-xs text-red-300">{state.recommendationError}</p>
                  )}

                  {state.recommendationStatus === 'done' && state.recommendation && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex flex-col gap-2 rounded-md bg-hs-mid/40 p-3 text-sm"
                    >
                      <div className="flex items-center gap-2">
                        <CloudRain className="h-4 w-4 text-hs-teal" />
                        <span>
                          {Math.round(state.recommendation.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                          {Math.round(state.recommendation.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Ruler className="mt-0.5 h-4 w-4 text-hs-teal" />
                        <div className="flex flex-col gap-1">
                          <span className="text-xs text-hs-muted">Pond size options (storage = annual runoff):</span>
                          {state.recommendation.pond_options.map((option) => (
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
                      {state.recommendation.available_land_hectares !== null && (
                        <p className="text-xs text-hs-muted/70">
                          ~{state.recommendation.available_land_hectares.toFixed(1)} ha of land available nearby
                          (excluding buildings, roads, and water bodies)
                        </p>
                      )}
                    </motion.div>
                  )}
                </motion.div>
              )}
            </motion.div>
          )}

        {state.status === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col gap-2 rounded-md bg-red-950/60 p-3 text-sm text-red-200"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              {state.errorMessage}
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
            >
              Retry
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
```

- [ ] **Step 2: Update the test file — remove the now-invalid idle test**

In `frontend/src/components/SitePanel.test.tsx`, delete this test (the `'idle'` case no longer exists in `SitePanel` — `IdleHint`, Task 3, covers it instead):

```tsx
  it('shows a prompt when idle', () => {
    render(<SitePanel state={baseState} onAnalyze={vi.fn()} onRetry={vi.fn()} onGetRecommendation={vi.fn()} />)
    expect(screen.getByText(/click anywhere/i)).toBeInTheDocument()
  })
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npx vitest run src/components/SitePanel.test.tsx`
Expected: PASS (7 remaining tests — locating indicator, located view, analyze button, elevation stats, recommendation button/display, error+retry)

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SitePanel.tsx frontend/src/components/SitePanel.test.tsx
git commit -m "Restyle SitePanel to Earth & Water; drop its now-redundant idle state"
```

---

### Task 9: Restyle and simplify `UploadPanel`

**Files:**
- Modify: `frontend/src/components/UploadPanel.tsx`
- Modify: `frontend/src/components/UploadPanel.test.tsx`

**Interfaces:**
- Consumes: `ContourUploadState` (unchanged type from `useContourUpload`).
- Produces: `export default function UploadPanel(props: { state: ContourUploadState; onRetry: () => void }): JSX.Element` — **prop signature changes**: `onUpload` and `onReset` are removed (file selection now happens entirely in `DropZoneOverlay`, Task 6, wired directly to `useContourUpload`'s `upload` in `App.tsx`); `onRetry` is added, and `App.tsx` (Task 11) wires it to reset the upload state and reopen the drop zone. `App.tsx` only ever mounts `UploadPanel` once `uploadState.status !== 'idle'`, so the old `'idle'` branch (the dashed-border upload button) is removed as dead code, along with the local `showRecommendation` toggle — `BottomSheet` (Task 7) now owns the reveal mechanic, so showing the full recommendation immediately once analyzed (rather than behind a second, redundant in-panel button) is correct.

- [ ] **Step 1: Replace `UploadPanel.tsx`**

Replace the full contents of `frontend/src/components/UploadPanel.tsx` with:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CloudRain, Droplets, Loader2, Ruler } from 'lucide-react'
import type { ContourUploadState } from '../hooks/useContourUpload'
import ContourLegend from './ContourLegend'

interface UploadPanelProps {
  state: ContourUploadState
  onRetry: () => void
}

export default function UploadPanel({ state, onRetry }: UploadPanelProps) {
  return (
    <AnimatePresence mode="wait">
      {state.status === 'uploading' && (
        <motion.div
          key="uploading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 text-sm text-hs-cream/80"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Analyzing {state.fileName}...
        </motion.div>
      )}

      {state.status === 'analyzed' && state.result && (
        <motion.div
          key="analyzed"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="flex flex-col gap-3"
        >
          <ContourLegend minElevation={state.result.min_elevation} maxElevation={state.result.max_elevation} />
          <div className="flex items-start gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
            <Droplets className="mt-0.5 h-4 w-4 text-hs-amber" />
            <div>
              <p className="font-medium">Recommended pond site</p>
              <p className="text-xs text-hs-muted">
                {state.result.pond_location.lat.toFixed(5)}, {state.result.pond_location.lon.toFixed(5)}
              </p>
              <p className="mt-1 text-xs text-hs-muted">
                Catchment area: {state.result.catchment_area_hectares.toFixed(1)} ha
              </p>
              <p className="text-xs text-hs-muted">
                Elevation: {Math.round(state.result.min_elevation)}m &ndash; {Math.round(state.result.max_elevation)}m
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 rounded-md bg-hs-mid/40 p-3 text-sm">
            <div className="flex items-center gap-2">
              <CloudRain className="h-4 w-4 text-hs-teal" />
              <span>
                {Math.round(state.result.average_annual_rainfall_mm)}mm/yr avg rainfall &rarr;{' '}
                {Math.round(state.result.runoff_volume_m3).toLocaleString()} m&sup3; runoff/yr
              </span>
            </div>
            <div className="flex items-start gap-2">
              <Ruler className="mt-0.5 h-4 w-4 text-hs-teal" />
              <div className="flex flex-col gap-1">
                <span className="text-xs text-hs-muted">Pond size options (storage = annual runoff):</span>
                {state.result.pond_options.map((option) => (
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
            {state.result.available_land_hectares !== null && (
              <p className="text-xs text-hs-muted/70">
                ~{state.result.available_land_hectares.toFixed(1)} ha of land available nearby (excluding
                buildings, roads, and water bodies)
              </p>
            )}
          </div>
        </motion.div>
      )}

      {state.status === 'error' && (
        <motion.div
          key="error"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex flex-col gap-2 rounded-md bg-red-950/60 p-3 text-sm text-red-200"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {state.errorMessage}
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
          >
            Try another file
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 2: Replace `UploadPanel.test.tsx`**

Replace the full contents of `frontend/src/components/UploadPanel.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ContourUploadState } from '../hooks/useContourUpload'
import UploadPanel from './UploadPanel'

const baseState: ContourUploadState = {
  status: 'uploading',
  result: null,
  errorMessage: null,
  fileName: 'contours.kml',
}

const result = {
  pond_location: { lat: 21.24, lon: 81.29 },
  catchment_area_m2: 495_900,
  catchment_area_hectares: 49.59,
  catchment_cell_count: 550,
  flow_accumulation_at_pond: 5206,
  catchment_boundary: [[81.28, 21.24]] as [number, number][],
  source_bbox: { min_lon: 81.28, min_lat: 21.24, max_lon: 81.31, max_lat: 21.26 },
  grid_resolution: 300,
  min_elevation: 267,
  max_elevation: 298,
  contours: [],
  average_annual_rainfall_mm: 1415.2,
  runoff_volume_m3: 175442.6,
  runoff_coefficient: 0.25,
  pond_options: [{ depth_m: 3, surface_area_m2: 58466, side_length_m: 241.8, fits_available_land: true }],
  available_land_hectares: 741.8,
}

describe('UploadPanel', () => {
  it('shows an uploading indicator while analyzing', () => {
    render(<UploadPanel state={baseState} onRetry={vi.fn()} />)
    expect(screen.getByText(/analyzing contours\.kml/i)).toBeInTheDocument()
  })

  it('shows the full recommendation immediately once analyzed', () => {
    render(<UploadPanel state={{ ...baseState, status: 'analyzed', result }} onRetry={vi.fn()} />)

    expect(screen.getByText(/catchment area: 49\.6 ha/i)).toBeInTheDocument()
    expect(screen.getByText(/3m deep.*242m square/)).toBeInTheDocument()
    expect(screen.getByText(/741\.8 ha of land available/)).toBeInTheDocument()
  })

  it('shows the error message and calls onRetry from the retry button', async () => {
    const onRetry = vi.fn()
    render(
      <UploadPanel
        state={{ ...baseState, status: 'error', errorMessage: 'could not parse contour KML' }}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText(/could not parse contour kml/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /try another file/i }))

    expect(onRetry).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npx vitest run src/components/UploadPanel.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (confirms no other file still calls `<UploadPanel onUpload=... onReset=... />` with the old prop names — `App.tsx` still does at this point in the plan, so this will actually FAIL until Task 11. That's expected and fine: commit this task's isolated change now, `App.tsx`'s call site gets fixed in Task 11.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadPanel.tsx frontend/src/components/UploadPanel.test.tsx
git commit -m "Restyle UploadPanel to Earth & Water; drop idle state and redundant reveal toggle"
```

---

### Task 10: Restyle `ContourLegend` and `LocateButton`

**Files:**
- Modify: `frontend/src/components/ContourLegend.tsx`
- Modify: `frontend/src/components/LocateButton.tsx`

**Interfaces:**
- Consumes/produces: unchanged for both — palette-only changes.

- [ ] **Step 1: Restyle `ContourLegend.tsx`**

Replace the full contents of `frontend/src/components/ContourLegend.tsx` with:

```tsx
import { contourGradientCss } from '../lib/contourColor'

interface ContourLegendProps {
  minElevation: number
  maxElevation: number
}

export default function ContourLegend({ minElevation, maxElevation }: ContourLegendProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="h-2 w-full rounded-full" style={{ background: contourGradientCss() }} />
      <div className="flex justify-between text-xs text-hs-muted">
        <span>{Math.round(minElevation)}m</span>
        <span>{Math.round(maxElevation)}m</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Restyle `LocateButton.tsx`**

Replace the full contents of `frontend/src/components/LocateButton.tsx` with:

```tsx
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
```

- [ ] **Step 3: Run their existing tests**

Run: `cd frontend && npx vitest run src/components/ContourLegend.test.tsx src/components/LocateButton.test.tsx`
Expected: PASS (both test files unchanged, still valid — neither asserts on color classes)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ContourLegend.tsx frontend/src/components/LocateButton.tsx
git commit -m "Restyle ContourLegend and LocateButton to Earth & Water"
```

---

### Task 11: Rewire `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `LoadingScreen` (Task 2), `IdleHint` (Task 3), `TopBar` (Task 5), `DropZoneOverlay` (Task 6), `BottomSheet` (Task 7), the restyled `SitePanel`/`UploadPanel` (Tasks 8–9, new `UploadPanel` signature `{ state, onRetry }`), `LocateButton` (unchanged signature), `MapView` (unchanged signature), `useSiteSelection`/`useContourUpload`/`useGeolocation` (all unchanged).
- Produces: the full app composition — nothing downstream of this task.

- [ ] **Step 1: Replace `App.tsx`**

Replace the full contents of `frontend/src/App.tsx` with:

```tsx
import { AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import BottomSheet from './components/BottomSheet'
import DropZoneOverlay from './components/DropZoneOverlay'
import IdleHint from './components/IdleHint'
import LoadingScreen from './components/LoadingScreen'
import LocateButton from './components/LocateButton'
import MapView from './components/MapView'
import SitePanel from './components/SitePanel'
import TopBar from './components/TopBar'
import UploadPanel from './components/UploadPanel'
import { useContourUpload } from './hooks/useContourUpload'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'

function App() {
  const { position, status: geoStatus, locate, requestId: geoRequestId } = useGeolocation()
  const { state, selectPoint, analyze, getFullRecommendation } = useSiteSelection()
  const { state: uploadState, upload, reset: resetUpload } = useContourUpload()
  const [isDropZoneOpen, setIsDropZoneOpen] = useState(false)

  // Once a file's been chosen and is uploading/analyzed/erroring, that
  // result takes over the map and bottom sheet -- entry is now via the
  // drop-zone overlay (Task 6) instead of a permanent tab, so this is
  // derived from upload state instead of a separately-tracked mode.
  const isUploadMode = uploadState.status !== 'idle'

  // state.lastPoint is set synchronously on click, before the reverse-geocode
  // round-trip resolves -- deriving from state.village instead left a beat of
  // nothing happening after every click while that request was in flight.
  const markerPosition = !isUploadMode ? state.lastPoint : null
  const contours = isUploadMode ? (uploadState.result?.contours ?? []) : (state.elevation?.contours ?? [])
  const catchmentBoundary = isUploadMode
    ? (uploadState.result?.catchment_boundary ?? null)
    : (state.elevation?.catchment_boundary ?? null)
  const pondLocation = isUploadMode ? (uploadState.result?.pond_location ?? null) : (state.elevation?.pond_location ?? null)
  const fitBoundsTo = isUploadMode ? (uploadState.result?.source_bbox ?? null) : null

  // requestId starts at 0 and only increments once useGeolocation's very
  // first locate() completes (success or failure) -- so this is precisely
  // "still waiting on the automatic on-load geolocation", not "any time
  // status happens to be 'locating'" (which would also be true for a later
  // manual re-locate via LocateButton, wrongly re-showing the loading
  // screen every time).
  const showLoadingScreen = geoRequestId === 0
  const showIdleHint = !isUploadMode && state.status === 'idle' && !isDropZoneOpen
  const showSiteSheet = !isUploadMode && state.status !== 'idle'
  const showUploadSheet = isUploadMode

  function handleFileChosen(file: File) {
    setIsDropZoneOpen(false)
    upload(file)
  }

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
        onMapClick={!isUploadMode ? selectPoint : () => {}}
        catchmentBoundary={catchmentBoundary}
        pondLocation={pondLocation}
        fitBoundsTo={fitBoundsTo}
        geoRequestId={geoRequestId}
      />

      <div className="absolute left-4 top-4 z-[1000] rounded-full bg-hs-panel/70 px-3 py-1.5 font-display text-sm font-semibold text-hs-cream backdrop-blur-md">
        HydroSage
      </div>

      <TopBar onResultSelected={selectPoint} onUploadClick={() => setIsDropZoneOpen(true)} />
      <LocateButton onClick={locate} status={geoStatus} />

      {showIdleHint && <IdleHint />}

      {showSiteSheet && (
        <BottomSheet expandable={state.status === 'analyzed'}>
          <SitePanel
            state={state}
            onAnalyze={analyze}
            onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
            onGetRecommendation={getFullRecommendation}
          />
        </BottomSheet>
      )}

      {showUploadSheet && (
        <BottomSheet expandable={uploadState.status === 'analyzed'}>
          <UploadPanel state={uploadState} onRetry={handleUploadRetry} />
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
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (this is the point where Task 9's `UploadPanel` prop-signature change finally gets consumed correctly)

- [ ] **Step 3: Run the full test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — every test file in the project (hooks, all restyled/new components)

- [ ] **Step 4: Production build**

Run: `cd frontend && npm run build`
Expected: builds clean

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "Rewire App.tsx: full-bleed map, TopBar, BottomSheet, DropZoneOverlay, LoadingScreen"
```

---

### Task 12: Live browser verification

**Files:** none (verification only)

**Interfaces:** none — this task exercises the whole app as built by Tasks 1–11.

- [ ] **Step 1: Start the dev server**

Run: `cd frontend && npm run dev` (background)
Verify: `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173` returns `200`

- [ ] **Step 2: Loading screen and idle state**

Using Playwright (or the project's established live-check pattern from earlier this session — a headless Chromium script under `/tmp/pw-runner` navigating to `http://localhost:5173`), verify:
- The loading screen (`HydroSage` wordmark + drawing contour lines) is visible immediately on load, then disappears.
- After it disappears, the idle-state pulsing hint ("Click anywhere to find a pond site") is visible over the map, and no `BottomSheet` is present (`document.querySelector('[data-testid="bottom-sheet-toggle"]')` should not exist, and there should be no results panel at all yet).
- Screenshot this state.

- [ ] **Step 3: Click-to-select flow**

Click a point on the map. Verify:
- A `BottomSheet` appears at the bottom, showing the village name (unexpandable — no chevron toggle yet, since `status` isn't `'analyzed'`).
- Click "Analyze this site". Verify the sheet now shows elevation/legend/pond-site info, and a chevron toggle appears (`expandable` is now true).
- Click the toggle (`[data-testid="bottom-sheet-toggle"]`). Verify the sheet expands, and clicking "Get pond recommendation" inside it shows the rainfall/runoff/pond-size/land-availability block.
- Screenshot both peeked and expanded states.

- [ ] **Step 4: KML-upload flow**

Click the upload icon in the `TopBar`. Verify the `DropZoneOverlay` opens. Upload the real sample file at `docs/private/contours_1m.kml` (gitignored, present in the main checkout at `C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\docs\private\contours_1m.kml` — copy it into this worktree temporarily if needed, or point Playwright's `setInputFiles` at that absolute path directly). Verify:
- The overlay closes and a `BottomSheet` appears showing the full recommendation immediately (no separate reveal button — this flow returns everything in one call).
- Screenshot this state.

- [ ] **Step 5: Locate-me button**

Click the `LocateButton`. Verify (via the network-request-interception technique used earlier this session — checking actual Esri tile request URLs for their zoom level, not just a screenshot) that the map recenters and zooms to at least the useful minimum.

- [ ] **Step 6: Check for console errors**

Verify no `pageerror` or console `error`-level messages were logged across the whole verification pass.

- [ ] **Step 7: Report and stop the dev server**

Summarize what was verified (with the screenshots), matching this project's established `docs/PROJECT_STATUS.md` update pattern if this is the end of a work session. Stop the dev server.
