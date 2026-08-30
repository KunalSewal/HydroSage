import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import IdleHint from './IdleHint'

describe('IdleHint', () => {
  it('shows the click-to-begin hint text', () => {
    render(<IdleHint />)
    expect(screen.getByText(/click anywhere to find a pond site/i)).toBeInTheDocument()
  })
})
