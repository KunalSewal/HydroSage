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
