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
  recommendationStatus: 'idle',
  recommendation: null,
  recommendationError: null,
}

describe('SitePanel', () => {
  it('shows a locating indicator', () => {
    render(<SitePanel state={{ ...baseState, status: 'locating' }} onAnalyze={vi.fn()} onRetry={vi.fn()} onGetRecommendation={vi.fn()} />)
    expect(screen.getByText(/locating/i)).toBeInTheDocument()
  })

  it('shows the village name and an Analyze button once located', () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    render(
      <SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={vi.fn()} onRetry={vi.fn()} onGetRecommendation={vi.fn()} />,
    )
    expect(screen.getByText('Bhilai')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyze this site/i })).toBeInTheDocument()
  })

  it('calls onAnalyze when the button is clicked', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const onAnalyze = vi.fn()
    render(<SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={onAnalyze} onRetry={vi.fn()} onGetRecommendation={vi.fn()} />)

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
      pond_location: { lat: 21.191, lon: 81.301 },
      catchment_area_m2: 500_000,
      catchment_area_hectares: 50,
      catchment_cell_count: 400,
      flow_accumulation_at_pond: 999,
      catchment_boundary: [[81.29, 21.18]] as [number, number][],
    }
    render(
      <SitePanel
        state={{ ...baseState, status: 'analyzed', village, elevation }}
        onAnalyze={vi.fn()}
        onRetry={vi.fn()}
        onGetRecommendation={vi.fn()}
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

  it('calls onGetRecommendation when the button is clicked', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const elevation = {
      village_id: 'v1',
      bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
      min_elevation: 250,
      max_elevation: 300,
      contours: [],
      pond_location: { lat: 21.191, lon: 81.301 },
      catchment_area_m2: 500_000,
      catchment_area_hectares: 50,
      catchment_cell_count: 400,
      flow_accumulation_at_pond: 999,
      catchment_boundary: [[81.29, 21.18]] as [number, number][],
    }
    const onGetRecommendation = vi.fn()
    render(
      <SitePanel
        state={{ ...baseState, status: 'analyzed', village, elevation }}
        onAnalyze={vi.fn()}
        onRetry={vi.fn()}
        onGetRecommendation={onGetRecommendation}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /get pond recommendation/i }))

    expect(onGetRecommendation).toHaveBeenCalledOnce()
  })

  it('shows pond size options and available land once a recommendation is done', () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const elevation = {
      village_id: 'v1',
      bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
      min_elevation: 250,
      max_elevation: 300,
      contours: [],
      pond_location: { lat: 21.191, lon: 81.301 },
      catchment_area_m2: 19_613.75,
      catchment_area_hectares: 1.96,
      catchment_cell_count: 22,
      flow_accumulation_at_pond: 999,
      catchment_boundary: [[81.29, 21.18]] as [number, number][],
    }
    const recommendation = {
      village_id: 'v1',
      catchment_area_hectares: 1.96,
      average_annual_rainfall_mm: 1436.4,
      runoff_volume_m3: 7043.4,
      runoff_coefficient: 0.25,
      pond_options: [{ depth_m: 3, surface_area_m2: 2347.8, side_length_m: 48.5, fits_available_land: true }],
      available_land_hectares: 1155.3,
    }
    render(
      <SitePanel
        state={{
          ...baseState,
          status: 'analyzed',
          village,
          elevation,
          recommendationStatus: 'done',
          recommendation,
        }}
        onAnalyze={vi.fn()}
        onRetry={vi.fn()}
        onGetRecommendation={vi.fn()}
      />,
    )

    expect(screen.getByText(/3m deep.*49m square/)).toBeInTheDocument()
    expect(screen.getByText(/1155\.3 ha of land available/)).toBeInTheDocument()
  })

  it('shows the error message and a retry button on error', async () => {
    const onRetry = vi.fn()
    render(
      <SitePanel
        state={{ ...baseState, status: 'error', errorMessage: "couldn't identify a site here" }}
        onAnalyze={vi.fn()}
        onRetry={onRetry}
        onGetRecommendation={vi.fn()}
      />,
    )
    expect(screen.getByText(/couldn't identify a site here/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
