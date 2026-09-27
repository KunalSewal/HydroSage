import { describe, expect, it } from 'vitest'
import { pondLabel } from './mapLabels'

describe('pondLabel', () => {
  it('states the expected yearly water volume and the catchment size', () => {
    expect(pondLabel(16483.2, 4.9035)).toBe('Pond site\n~16,483 m³ water/yr\nCatchment 4.9 ha')
  })

  it('leaves out the volume while it is unknown', () => {
    expect(pondLabel(null, 4.9)).toBe('Pond site\nCatchment 4.9 ha')
    expect(pondLabel(undefined, 4.9)).toBe('Pond site\nCatchment 4.9 ha')
  })

  it('is just the site name with nothing else known', () => {
    expect(pondLabel(null, undefined)).toBe('Pond site')
  })
})
