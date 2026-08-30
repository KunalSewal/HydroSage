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
