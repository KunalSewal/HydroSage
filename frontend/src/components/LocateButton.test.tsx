import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import LocateButton from './LocateButton'

describe('LocateButton', () => {
  it('calls onClick when clicked', async () => {
    const onClick = vi.fn()
    render(<LocateButton onClick={onClick} status="located" />)

    await userEvent.click(screen.getByRole('button', { name: /locate me/i }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows a spinner while locating', () => {
    render(<LocateButton onClick={vi.fn()} status="locating" />)
    expect(screen.getByRole('button', { name: /locate me/i })).toBeInTheDocument()
  })
})
