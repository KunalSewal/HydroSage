import '@testing-library/jest-dom/vitest'

// jsdom implements no layout engine and so ships no ResizeObserver. Components
// that measure themselves (BottomSheet reporting its height to the map) would
// otherwise throw on mount in every test that renders them.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
