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
