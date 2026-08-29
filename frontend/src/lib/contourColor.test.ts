import { describe, expect, it } from 'vitest'
import { contourColor, contourGradientCss } from './contourColor'

describe('contourColor', () => {
  it('gives the lowest elevation a distinct color from the highest', () => {
    const low = contourColor(100, 100, 200)
    const high = contourColor(200, 100, 200)
    expect(low).not.toBe(high)
  })

  it('gives a mid elevation a color distinct from both ends', () => {
    const low = contourColor(100, 100, 200)
    const mid = contourColor(150, 100, 200)
    const high = contourColor(200, 100, 200)
    expect(mid).not.toBe(low)
    expect(mid).not.toBe(high)
  })

  it('is deterministic for the same inputs', () => {
    expect(contourColor(175, 100, 200)).toBe(contourColor(175, 100, 200))
  })

  it('does not blow up when every contour is at the same elevation', () => {
    expect(() => contourColor(150, 150, 150)).not.toThrow()
  })

  it('clamps elevations outside the given range instead of extrapolating oddly', () => {
    const belowMin = contourColor(50, 100, 200)
    const atMin = contourColor(100, 100, 200)
    expect(belowMin).toBe(atMin)
  })
})

describe('contourGradientCss', () => {
  it('produces a usable CSS linear-gradient string', () => {
    expect(contourGradientCss()).toMatch(/^linear-gradient\(to right, .+\)$/)
  })

  it('starts and ends with the same colors contourColor gives the extremes', () => {
    const css = contourGradientCss()
    expect(css).toContain(contourColor(0, 0, 1))
    expect(css).toContain(contourColor(1, 0, 1))
  })
})
