import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import SearchBox from './SearchBox'

vi.mock('../api/client')

describe('SearchBox', () => {
  beforeEach(() => {
    vi.mocked(client.searchPlaces).mockReset()
  })

  it('shows results and calls onResultSelected when one is clicked', async () => {
    vi.mocked(client.searchPlaces).mockResolvedValue([{ display_name: 'Bhilai, Chhattisgarh', lat: 21.19, lon: 81.3 }])
    const onResultSelected = vi.fn()
    render(<SearchBox onResultSelected={onResultSelected} />)

    await userEvent.type(screen.getByPlaceholderText(/search a place/i), 'Bhilai{Enter}')
    await screen.findByText('Bhilai, Chhattisgarh')
    await userEvent.click(screen.getByText('Bhilai, Chhattisgarh'))

    expect(onResultSelected).toHaveBeenCalledWith(21.19, 81.3)
  })

  it('shows a no-results message when the search succeeds with nothing found', async () => {
    vi.mocked(client.searchPlaces).mockResolvedValue([])
    render(<SearchBox onResultSelected={vi.fn()} />)

    await userEvent.type(screen.getByPlaceholderText(/search a place/i), 'Nowhereville{Enter}')

    expect(await screen.findByText(/no places found/i)).toBeInTheDocument()
  })

  it('shows an error message when the search fails, instead of crashing silently', async () => {
    vi.mocked(client.searchPlaces).mockRejectedValue(new Error('geocoding service unavailable'))
    render(<SearchBox onResultSelected={vi.fn()} />)

    await userEvent.type(screen.getByPlaceholderText(/search a place/i), 'Bhilai{Enter}')

    expect(await screen.findByText('geocoding service unavailable')).toBeInTheDocument()
  })

  it('does not search on an empty query', async () => {
    render(<SearchBox onResultSelected={vi.fn()} />)

    await userEvent.type(screen.getByPlaceholderText(/search a place/i), '{Enter}')

    expect(client.searchPlaces).not.toHaveBeenCalled()
  })
})
