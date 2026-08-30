import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LoadingScreen from './LoadingScreen'

describe('LoadingScreen', () => {
  it('shows the HydroSage wordmark', () => {
    render(<LoadingScreen />)
    expect(screen.getByTestId('loading-screen')).toBeInTheDocument()
    expect(screen.getByText('HydroSage')).toBeInTheDocument()
  })
})
