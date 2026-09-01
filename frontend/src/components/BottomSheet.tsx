import { motion } from 'framer-motion'
import { ChevronUp } from 'lucide-react'
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

interface BottomSheetProps {
  expandable?: boolean
  onHeightChange?: (height: number) => void
  children: ReactNode
}

const PEEK_MAX_HEIGHT = '100px'
// Viewport-relative so the sheet adapts to the screen instead of eating a
// laptop viewport whole -- results need room, but the map has to stay legible
// above it, since that's where the catchment is being framed.
const EXPANDED_MAX_HEIGHT = '55vh'
const UNCLIPPED_MAX_HEIGHT = '2000px' // effectively "no limit" -- framer-motion animates maxHeight more reliably between two lengths than between a length and 'none'

// A Google-Maps-style peek/expand results panel, replacing the old fixed
// sidebar. `expandable` is only true once there's real content worth
// hiding (the click-map flow's post-"analyzed" state, or the KML-upload
// flow's post-"analyzed" state) -- earlier, shorter states (e.g. "Locating...")
// render at full, unclipped height with no toggle at all.
export default function BottomSheet({ expandable = false, onHeightChange, children }: BottomSheetProps) {
  const [expanded, setExpanded] = useState(expandable)
  const [wasExpandable, setWasExpandable] = useState(expandable)
  const elementRef = useRef<HTMLDivElement>(null)

  // Results arriving is the moment the user wants to read them, so the sheet
  // opens itself rather than leaving them to find the chevron. Collapsing is
  // still theirs to choose: this fires only on the transition into
  // `expandable`, so a manual collapse isn't undone on the next render.
  //
  // Adjusted during render rather than in an effect (React's documented
  // prop-change pattern) -- an effect would paint the 100px peek for a frame
  // before expanding, which is the flash this change exists to remove.
  if (expandable !== wasExpandable) {
    setWasExpandable(expandable)
    if (expandable) setExpanded(true)
  }

  // The map fits the catchment into the strip above this sheet, so it needs the
  // sheet's real height. Measured rather than shared as a constant: the panels
  // vary in length, and maxHeight is only a cap.
  useLayoutEffect(() => {
    const element = elementRef.current
    if (!element || !onHeightChange) return

    const report = () => onHeightChange(element.offsetHeight)
    report()

    const observer = new ResizeObserver(report)
    observer.observe(element)
    return () => {
      observer.disconnect()
      // Without this the map keeps padding for a sheet that's gone.
      onHeightChange(0)
    }
  }, [onHeightChange])

  const maxHeight = expandable ? (expanded ? EXPANDED_MAX_HEIGHT : PEEK_MAX_HEIGHT) : UNCLIPPED_MAX_HEIGHT

  return (
    <motion.div
      ref={elementRef}
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
