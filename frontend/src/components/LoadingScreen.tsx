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
