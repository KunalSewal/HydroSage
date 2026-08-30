# HydroSage frontend redesign — design spec

Date: 2026-08-30
Status: Approved by user across 4 visual-companion rounds (see below); ready for implementation planning.

## Context

The functional pipeline is complete (terrain → catchment → rainfall → runoff → pond sizing → land availability, on both the click-map and KML-upload flows). The user's complaint is specifically about visual polish: *"I open the site and it straight opens the map, whole big map, on right side a small column with basic click site and upload file option thats it. Too basic... let me know if you can design something great, have animations where they would fit. A loading screen to open site or something."*

This spec covers **frontend only** — no backend changes, no changes to the analysis methodology (catchment sizing, dimensions, etc., which the user will evaluate separately afterward). Scope: `frontend/src/` — visual design system, layout restructuring, and the new interaction patterns below.

## Process note

Brainstormed via the visual-companion tool across 4 rounds, each confirmed live by the user ("love it" / decisive repeated clicks) rather than assumed:
1. Visual direction — chose **"Earth & Water"** over a topographic/cyan-glow direction and a generic Linear-style dark-indigo direction.
2. Layout — chose **map-dominant with a floating panel** over a refined-but-still-fixed sidebar.
3. Loading screen — chose an **animated contour-line-draw-in** concept (live-previewed, not a static mock).
4. Bottom sheet interaction — chose a **Google-Maps-style peek/expand sheet** (live click-to-try demo) over keeping any fixed panel.
5. Upload entry point — chose **folding "upload a KML" into the search bar as a secondary icon**, opening a drop-zone overlay on demand, over keeping the old permanent tab toggle.

## Visual design system

**Palette** ("Earth & Water" — deep forest green + warm sand/amber, consolidated from the mockups' actual values):

| Token | Hex | Use |
|---|---|---|
| `bg-deep` | `#0a231d` | Base background (radial/linear gradient with `bg-mid`) |
| `bg-mid` | `#163d33` / `#1a3a30` | Gradient partner, panel-adjacent surfaces |
| `panel` | `rgba(15,43,36,0.92)` | Bottom sheet / floating card background (with backdrop-blur) |
| `panel-subtle` | `rgba(253,246,236,0.06)` | Stat-card fills inside panels |
| `border-amber` | `rgba(245,194,107,0.2–0.3)` | Panel borders, dashed drop-zone border |
| `accent-amber` | `#f5c26b` | Primary accent — CTAs, active states, the idle-hint pulse |
| `accent-teal` | `#5fc9ba` | Secondary accent — contour/ripple motifs, secondary stats |
| `text-cream` | `#fdf6ec` | Primary text on dark surfaces |
| `text-muted` | `#a8d8ce` | Secondary/label text |

This replaces the current `slate-900`/`sky-400`/`amber-400` Tailwind defaults entirely — extend Tailwind's theme with these as named tokens (`bg-deep`, `accent-amber`, etc.) rather than hardcoding hex values in components, so the palette stays swappable/consistent.

**Typography:** `Fraunces` (serif, weight 600) for the wordmark and headings — loaded via Google Fonts, the one exception to "no external assets" the artifact sandbox allows and this is a real app, not a sandboxed artifact, so no such restriction applies anyway. Body/UI text stays a clean system sans (`Segoe UI`/system stack, or `Inter` via Google Fonts for tighter cross-platform consistency — pick during implementation, low-stakes). Data readouts (elevation, hectares, m³) keep their current plain numeric styling; no monospace treatment (that was part of the topographic direction that wasn't chosen).

**Motion principles:**
- Bottom sheet expand/collapse: spring-ish ease (`cubic-bezier(0.22,1,0.36,1)` as previewed), ~450ms.
- Idle-state hint: a slow, continuous ping/pulse (`~2s ease-out infinite`) on a dot at the map's center — never stops, since it's the "the map isn't empty, it's waiting for you" signal.
- Loading screen: contour paths draw in via `stroke-dashoffset` animation, staggered starts (0.1s/0.4s/0.7s/1s), each ~2.4–3s — then the whole loading screen wipes away as the map beneath is revealed (implementation detail: likely an `AnimatePresence` exit transition once `useGeolocation`'s first result — success or failure — resolves, so the loading screen's duration is tied to real readiness, not a fixed timer).
- Existing count-up (elevation stats) and staggered contour-reveal patterns are kept as-is — they already fit this direction, no rework needed.

**Icons:** keep `lucide-react` (already a dependency, comprehensive, consistent stroke weight) — just restyle colors to the new palette. No icon library change.

## Layout & components

**Top-level structure change:** the current `App.tsx` two-column flex (`map | 320px sidebar`) is replaced by a single full-bleed `MapView`, with everything else as floating overlays positioned absolutely over it:
- Top-center: a single pill-shaped bar combining the search input and an upload icon button (replaces `SearchBox` + the old tab toggle). Clicking the upload icon opens the drop-zone overlay; clicking outside or its own close button dismisses it.
- Top-left: a small brand mark ("HydroSage" in Fraunces).
- Top-right: `LocateButton`, restyled to the new palette, unchanged behavior (already fixed this session — zoom + `requestId`-based re-trigger).
- Idle-state hint: a pulsing dot + short label ("Click anywhere to find a pond site"), shown only when there's no site selected and no upload result — replaces the current idle text in the old sidebar.
- Bottom: the new `BottomSheet` component, replacing `SitePanel`/`UploadPanel`'s role as the fixed results area. Peek state shows a one-line title + subtitle; expanded state shows everything the current panels show (elevation, legend, pond site, and — behind their own existing "Get pond recommendation" button, unchanged — the full rainfall/runoff/pond-options/land-availability block). Expand/collapse toggles on click (drag-gesture support is a natural mobile follow-up, not required for this pass).
- Drop-zone overlay: a full-map translucent overlay with a dashed-border card, shown only while open; replaces the current `UploadPanel`'s idle-state upload button. Once a file's chosen, the overlay closes and the same `BottomSheet` shows the KML-flow's results (reusing `useContourUpload`, unchanged hook logic).

**What's reused unchanged:** `useSiteSelection`, `useContourUpload`, `useGeolocation` (all hook logic — this redesign is presentation-layer only), `ContourLegend`, the recommendation-rendering logic inside `SitePanel`/`UploadPanel` (moves into `BottomSheet`'s expanded content, not rewritten from scratch), `MapView`'s map/marker/contour/boundary rendering (only the floating-chrome layer around it changes).

**New components:** `LoadingScreen.tsx` (shown on initial mount until geolocation resolves), `BottomSheet.tsx` (replaces the sidebar's role), `TopBar.tsx` or similar (search + upload icon combined), `DropZoneOverlay.tsx`. `SitePanel.tsx`/`UploadPanel.tsx` either get absorbed into `BottomSheet`'s content or kept as the content renderers `BottomSheet` wraps — implementation detail to settle in the plan, not a design-level decision.

## Explicitly out of scope

- Any backend/API change (confirmed with the user).
- Catchment sizing, runoff methodology, or any analysis-correctness work — the user will evaluate that separately once this redesign lands.
- Mobile-specific drag-gesture support for the bottom sheet (click-to-expand is the agreed baseline; touch drag is a natural future enhancement, not required now).
- A full custom icon set or illustration system beyond what's described above.

## Testing approach

Existing test coverage (hooks, `SitePanel`/`UploadPanel` content assertions, `SearchBox`, `LocateButton`) should largely carry over by testing whatever component now renders that content (e.g. `BottomSheet`'s expanded state), not be thrown away — this is a presentation restructuring, not a logic rewrite. New components (`LoadingScreen`, `BottomSheet`'s peek/expand toggle, `DropZoneOverlay`'s open/close) get their own tests following this codebase's established patterns (Vitest + Testing Library, `userEvent` for interaction). Live browser verification via Playwright before considering any piece done, same as every other feature this session.
