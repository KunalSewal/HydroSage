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
