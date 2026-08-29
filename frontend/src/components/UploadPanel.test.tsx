import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ContourUploadState } from '../hooks/useContourUpload'
import UploadPanel from './UploadPanel'

const baseState: ContourUploadState = {
  status: 'idle',
  result: null,
  errorMessage: null,
  fileName: null,
}

const result = {
  pond_location: { lat: 21.24, lon: 81.29 },
  catchment_area_m2: 495_900,
  catchment_area_hectares: 49.59,
  catchment_cell_count: 550,
  flow_accumulation_at_pond: 5206,
  catchment_boundary: [[81.28, 21.24]] as [number, number][],
  source_bbox: { min_lon: 81.28, min_lat: 21.24, max_lon: 81.31, max_lat: 21.26 },
  grid_resolution: 300,
  min_elevation: 267,
  max_elevation: 298,
  contours: [],
  average_annual_rainfall_mm: 1415.2,
  runoff_volume_m3: 175442.6,
  runoff_coefficient: 0.25,
  pond_options: [{ depth_m: 3, surface_area_m2: 58466, side_length_m: 241.8, fits_available_land: true }],
  available_land_hectares: 741.8,
}

describe('UploadPanel', () => {
  it('shows the upload prompt when idle', () => {
    render(<UploadPanel state={baseState} onUpload={vi.fn()} onReset={vi.fn()} />)
    expect(screen.getByText(/upload contour map/i)).toBeInTheDocument()
  })

  it('shows the recommendation once a file is analyzed', () => {
    render(
      <UploadPanel
        state={{ ...baseState, status: 'analyzed', result }}
        onUpload={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(screen.getByText(/catchment area: 49\.6 ha/i)).toBeInTheDocument()
    expect(screen.getByText(/3m deep.*242m square/)).toBeInTheDocument()
    expect(screen.getByText(/741\.8 ha of land available/)).toBeInTheDocument()
  })

  it('shows the error message on failure', () => {
    render(
      <UploadPanel
        state={{ ...baseState, status: 'error', errorMessage: 'could not parse contour KML' }}
        onUpload={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByText(/could not parse contour kml/i)).toBeInTheDocument()
  })
})
