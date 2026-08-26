import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SiteSelectionState } from '../hooks/useSiteSelection'
import SitePanel from './SitePanel'

const baseState: SiteSelectionState = {
  status: 'idle',
  village: null,
  elevation: null,
  errorMessage: null,
  lastPoint: null,
}

describe('SitePanel', () => {
  it('shows a prompt when idle', () => {
    render(<SitePanel state={baseState} onAnalyze={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText(/click anywhere/i)).toBeInTheDocument()
  })

  it('shows a locating indicator', () => {
    render(<SitePanel state={{ ...baseState, status: 'locating' }} onAnalyze={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText(/locating/i)).toBeInTheDocument()
  })

  it('shows the village name and an Analyze button once located', () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    render(
      <SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={vi.fn()} onRetry={vi.fn()} />,
    )
    expect(screen.getByText('Bhilai')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyze this site/i })).toBeInTheDocument()
  })

  it('calls onAnalyze when the button is clicked', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const onAnalyze = vi.fn()
    render(<SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={onAnalyze} onRetry={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /analyze this site/i }))

    expect(onAnalyze).toHaveBeenCalledOnce()
  })

  it('shows elevation stats once analyzed', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const elevation = {
      village_id: 'v1',
      bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
      min_elevation: 250,
      max_elevation: 300,
      contours: [],
    }
    render(
      <SitePanel
        state={{ ...baseState, status: 'analyzed', village, elevation }}
        onAnalyze={vi.fn()}
        onRetry={vi.fn()}
      />,
    )
    // The numbers count up via requestAnimationFrame rather than snapping
    // in (see the spec's animation section), so this needs to wait for the
    // animation to settle rather than assert synchronously. Each number is
    // queried by its own data-testid and awaited individually -- min and max
    // animate together, but max's climb passes through min's target value on
    // its way to its own target, so a shared, unanchored text match (e.g.
    // getByText(/250/) against the combined "Elevation Xm - Ym" string) can
    // resolve on that transient value instead of min's genuine settled one.
    await waitFor(() => expect(screen.getByTestId('min-elevation')).toHaveTextContent('250'), { timeout: 1000 })
    await waitFor(() => expect(screen.getByTestId('max-elevation')).toHaveTextContent('300'), { timeout: 1000 })
  })

  it('shows the error message and a retry button on error', async () => {
    const onRetry = vi.fn()
    render(
      <SitePanel
        state={{ ...baseState, status: 'error', errorMessage: "couldn't identify a site here" }}
        onAnalyze={vi.fn()}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText(/couldn't identify a site here/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
