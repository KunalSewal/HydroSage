import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ContourLegend from './ContourLegend'

describe('ContourLegend', () => {
  it('shows the min and max elevation labels', () => {
    render(<ContourLegend minElevation={267.4} maxElevation={298.9} />)
    expect(screen.getByText('267m')).toBeInTheDocument()
    expect(screen.getByText('299m')).toBeInTheDocument()
  })
})
