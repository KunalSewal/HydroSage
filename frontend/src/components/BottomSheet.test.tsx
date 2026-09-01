import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BottomSheet from './BottomSheet'

describe('BottomSheet', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders children directly with no toggle when not expandable', () => {
    render(
      <BottomSheet>
        <p>Hello</p>
      </BottomSheet>,
    )
    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.queryByTestId('bottom-sheet-toggle')).not.toBeInTheDocument()
  })

  // Results used to land in a 100px peek that hid everything below the first
  // line, so every analysis ended with the user hunting for the chevron.
  it('starts expanded once it becomes expandable, and collapses on click', async () => {
    render(
      <BottomSheet expandable>
        <p>Details</p>
      </BottomSheet>,
    )
    const toggle = screen.getByTestId('bottom-sheet-toggle')
    expect(toggle).toHaveAttribute('aria-label', 'Collapse details')

    await userEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-label', 'Expand details')
  })

  // `expandable` flips from false to true when the analysis resolves, and the
  // sheet stays mounted across that transition -- so auto-expansion has to be
  // driven by the prop changing, not merely by the initial mount state.
  it('expands when results arrive in an already-mounted sheet', () => {
    const { rerender } = render(
      <BottomSheet>
        <p>Analyzing...</p>
      </BottomSheet>,
    )
    expect(screen.queryByTestId('bottom-sheet-toggle')).not.toBeInTheDocument()

    rerender(
      <BottomSheet expandable>
        <p>Results</p>
      </BottomSheet>,
    )

    expect(screen.getByTestId('bottom-sheet-toggle')).toHaveAttribute('aria-label', 'Collapse details')
  })

  // The map fits the catchment into the strip left above this sheet, so it
  // needs the sheet's real height -- a shared constant would drift the moment
  // the panel's content changes.
  it('reports its rendered height to its parent', () => {
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(240)
    const onHeightChange = vi.fn()

    render(
      <BottomSheet expandable onHeightChange={onHeightChange}>
        <p>Details</p>
      </BottomSheet>,
    )

    expect(onHeightChange).toHaveBeenCalledWith(240)
  })

  it('reports a zero height when it unmounts, so the map reclaims the space', () => {
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(240)
    const onHeightChange = vi.fn()

    const { unmount } = render(
      <BottomSheet expandable onHeightChange={onHeightChange}>
        <p>Details</p>
      </BottomSheet>,
    )
    unmount()

    expect(onHeightChange).toHaveBeenLastCalledWith(0)
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
