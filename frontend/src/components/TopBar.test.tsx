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
