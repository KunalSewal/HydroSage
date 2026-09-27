// leaflet-geoman is a classic Leaflet plugin: at load time it reads Leaflet
// from the global `L` and extends it. An ES-module import of leaflet never
// sets that global, so the plugin crashed with "L is not defined" and the
// whole app rendered blank. MapView imports this module *before* geoman --
// imports evaluate in order, so the global exists by the time geoman runs.
import L from 'leaflet'

declare global {
  interface Window {
    L: typeof L
  }
}

window.L = L
