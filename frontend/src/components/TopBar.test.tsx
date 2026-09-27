import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import TopBar from './TopBar'

function renderTopBar(overrides: Partial<Parameters<typeof TopBar>[0]> = {}) {
  const props = { onResultSelected: vi.fn(), onUploadClick: vi.fn(), onDrawClick: vi.fn(), ...overrides }
  render(<TopBar {...props} />)
  return props
}

describe('TopBar', () => {
  it('renders the search input', () => {
    renderTopBar()
    expect(screen.getByPlaceholderText(/search a place/i)).toBeInTheDocument()
  })

  it('calls onUploadClick when the upload icon is clicked', async () => {
    const { onUploadClick } = renderTopBar()

    await userEvent.click(screen.getByRole('button', { name: /upload a contour map/i }))

    expect(onUploadClick).toHaveBeenCalledOnce()
  })

  it('starts a polygon drawing from the draw-area icon', async () => {
    const { onDrawClick } = renderTopBar()

    await userEvent.click(screen.getByRole('button', { name: /^draw a land area$/i }))

    expect(onDrawClick).toHaveBeenCalledWith('Polygon')
  })

  it('starts a rectangle drawing from the rectangle icon', async () => {
    const { onDrawClick } = renderTopBar()

    await userEvent.click(screen.getByRole('button', { name: /draw a rectangular land area/i }))

    expect(onDrawClick).toHaveBeenCalledWith('Rectangle')
  })
})
