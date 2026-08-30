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
