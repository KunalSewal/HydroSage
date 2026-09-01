# HydroSage — Phase 1 Report

**Estimating pond catchments from a contour map**

Kunal Sewal · 12341270

---

## Submission details

| | |
|---|---|
| **Repository** | https://github.com/KunalSewal/HydroSage |
| **API endpoint** | `POST http://10.1.75.53:3265/analyzeContour` |
| **Form field name** | `contour_map` *(required)* |
| **Accepted formats** | `.kml`, `.kmz` |
| **Encoding** | `multipart/form-data` |

No authentication, headers, or query parameters are required.

```bash
curl -X POST http://10.1.75.53:3265/analyzeContour \
  -F "contour_map=@contours_1m.kml"
```

> **Expected response time.** A full analysis of the 6.7 MB sample map takes roughly
> **20–60 seconds**: the file carries 1,355 contour lines that are interpolated onto a
> 90,000-cell grid before flow routing runs. This is normal, not a hang. Allow a
> generous client timeout.

---

## How the catchment is estimated

A contour map is a set of elevation isolines, not a surface. The analysis therefore
reconstructs a continuous surface first, then routes water across it using standard D8
flow modelling, and finally delineates the area draining to a chosen point. Every value
is derived from the uploaded file — no coordinates, elevations, or areas are hard-coded.

### 1. Read the contour geometry

Each KML `Placemark` containing a `LineString` is read as one contour line, taking its
elevation from the placemark's `<name>` and its vertices from the `<coordinates>` list. A
KMZ is unzipped first, with its uncompressed entry size checked beforehand so a malformed
archive cannot exhaust memory.

*`backend/app/infrastructure/kml_parser.py`*

### 2. Interpolate a continuous elevation surface

Every contour vertex becomes a 3-D sample. Those samples are interpolated onto a
**300 × 300 grid** spanning the file's own bounding box using linear interpolation. Cells
outside the survey's convex hull cannot be interpolated, so they are filled by
nearest-neighbour and flagged in a validity mask, which travels with the grid so
extrapolated filler is never later mistaken for real terrain.

*`scipy.interpolate.griddata`*

### 3. Locate genuine depressions — before conditioning

A cell is a depression if it sits at or below every neighbour in its 3 × 3 window. This
runs on the **raw** grid, because the conditioning in the next step deliberately erases
depressions; detecting them afterwards would find none. Cells flagged as interpolated
filler are excluded, and a margin around the edge is ignored.

*`scipy.ndimage.minimum_filter`*

### 4. Condition the surface and route the flow

Pits are filled, depressions flooded, and flat areas resolved, so that every cell has a
defined downhill neighbour. D8 flow directions are then computed, and flow accumulation
counts how many upslope cells drain through each cell — the standard measure of where
water concentrates.

*`pysheds`: `fill_pits` → `fill_depressions` → `resolve_flats` → `flowdir` → `accumulation`*

### 5. Choose a pond site

Candidates are sampled across the grid and ranked by flow accumulation, with genuine
depressions preferred over bare accumulation maxima — a natural hollow needs less
excavation and holds water without a bund. Each candidate's catchment is traced and kept
only if its area falls within the target band. The site is addressed by **grid index
rather than coordinate**, so the traced catchment is guaranteed to contain the site it was
traced from.

*Target band 1–5 ha · 20 × 20 sampling divisions*

### 6. Delineate the catchment

All cells draining to the chosen site are traced through the D8 directions. Cell count
times per-cell ground area gives the catchment area, and the mask's outline is vectorised
into a closed boundary ring returned as coordinates.

As a correctness check, **the traced cell count must equal the flow accumulation reported
at that site** — the two are the same quantity computed by different routes.

### 7. Size the pond against two physical bounds

A flood-fill raises a water level from the site in 40 steps, integrating area against
depth to measure what the landform can actually hold, and stopping if the water would
spill. Separately, annual runoff is estimated as rainfall × catchment area × a runoff
coefficient. Each candidate depth is sized to the **smaller** of the two: a basin bigger
than the water available would sit part-full, and a volume the land cannot hold is not a
pond.

*Depths 2 m / 3 m / 4 m · runoff coefficient 0.25*

### Why the catchment is capped at 5 hectares

Indian watershed practice treats two structures separately: a **farm pond**, a dug
excavation serving a few hectares, and a **check dam** or percolation tank, a bund across
a drainage line serving tens of hectares. An earlier 1–50 ha band returned
check-dam-scale results and described them as ponds. Constraining site selection to
1–5 ha targets farm-pond scale at the cause, rather than clamping the output afterwards.

---

## Demonstration

Sample contour map · 6.7 MB · 1,355 contour lines at 1 m interval.

Posting the provided sample map returns HTTP 200 with the following analysis. The site
lies in the surveyed area's southern valley floor, and the catchment traced from it covers
4.35 hectares.

| Catchment area | Catchment cells | Flow accumulation | Elevation range | Contour lines |
|---|---|---|---|---|
| **4.35 ha** | **457** | **457** | **31 m** | **1,355** |

Cell count and flow accumulation agreeing exactly is the correctness check described
above: in D8 routing the number of cells draining to a point *is* the accumulation at that
point, so any disagreement would indicate the catchment had been traced from the wrong
cell.

### Response (abridged)

```json
{
  "pond_location": { "lat": 21.242871412836838, "lon": 81.30447177886963 },
  "catchment_area_m2": 43530.35752952682,
  "catchment_area_hectares": 4.353035752952682,
  "catchment_cell_count": 457,
  "flow_accumulation_at_pond": 457.0,
  "catchment_boundary": [ [81.30504455566405, 21.243227785895062] ],
  "source_bbox": {
    "min_lon": 81.2814044952393, "min_lat": 21.2398224433387,
    "max_lon": 81.3126468658447, "max_lat": 21.2635806472203
  },
  "grid_resolution": 300,
  "min_elevation": 267.0,
  "max_elevation": 298.0,
  "average_annual_rainfall_mm": 1415.2,
  "runoff_volume_m3": 15401.0,
  "runoff_coefficient": 0.25,
  "pond_options": [
    { "depth_m": 2.0, "surface_area_m2": 3950.6, "side_length_m": 62.9, "runoff_capture_ratio": 0.513 },
    { "depth_m": 3.0, "surface_area_m2": 5133.7, "side_length_m": 71.6, "runoff_capture_ratio": 1.0 },
    { "depth_m": 4.0, "surface_area_m2": 3850.3, "side_length_m": 62.1, "runoff_capture_ratio": 1.0 }
  ],
  "contours": []
}
```

`catchment_boundary` is truncated above — the real response carries a closed ring of 53
points. `contours` carries all 1,355 lines at the KML's original precision.

### Reading the pond options

The capture ratio identifies which bound is binding. At 2 m the pond is
**terrain-limited** — the landform holds only 51% of the year's runoff, and the rest would
overflow. At 3 m and 4 m it is **runoff-limited**: the terrain could hold more, but the
catchment does not deliver more, so the pond is sized to the water that actually arrives
rather than to the hole that could be dug.

---

## API documentation

### `POST /analyzeContour`

#### Request

| Field | Type | Notes |
|---|---|---|
| `contour_map` | file | The contour map. `.kml` or `.kmz`. **Required.** |

#### Response fields

| Field | Type | Description |
|---|---|---|
| `pond_location` | object | Recommended pond site as `lat` / `lon`. |
| `catchment_area_m2` | number | Delineated catchment area in square metres. |
| `catchment_area_hectares` | number | The same area in hectares. |
| `catchment_cell_count` | integer | Grid cells draining to the site. |
| `flow_accumulation_at_pond` | number | D8 accumulation at the site. Equals the cell count when the analysis is self-consistent. |
| `catchment_boundary` | array | Closed ring of `[lon, lat]` pairs outlining the catchment. |
| `source_bbox` | object | Geographic extent of the uploaded map. |
| `grid_resolution` | integer | Analysis grid size per side (300). |
| `min_elevation` / `max_elevation` | number | Elevation range across the interpolated surface, in metres. |
| `contours` | array | The map's own contour lines at original precision: `elevation` plus `[lon, lat]` coordinates. |
| `average_annual_rainfall_mm` | number \| null | Ten-year mean annual rainfall at the map's centroid. |
| `runoff_volume_m3` | number \| null | Estimated annual runoff reaching the site. |
| `runoff_coefficient` | number \| null | Fraction of rainfall assumed to become runoff. |
| `pond_options` | array | One sizing option per candidate depth. |
| `available_land_hectares` | number \| null | Land free of buildings, roads and water bodies nearby. |

#### Pond option fields

| Field | Type | Description |
|---|---|---|
| `depth_m` | number | Candidate excavation depth: 2, 3 or 4 metres. |
| `surface_area_m2` | number | Footprint needed to hold the bounded volume at this depth. |
| `side_length_m` | number | The same footprint expressed as a square's side. |
| `runoff_capture_ratio` | number \| null | Share of annual runoff held. Below 1.0 is terrain-limited; exactly 1.0 is runoff-limited. |
| `fits_available_land` | boolean \| null | Whether the footprint fits the land available nearby. |

#### Status codes

| Code | Meaning |
|---|---|
| `200` | Analysis complete. |
| `422` | Missing `contour_map` field, a file that is not `.kml`/`.kmz`, or a file that cannot be parsed as contour geometry. The message names the cause. |

> **Degraded responses.** Rainfall and land-use figures come from third-party services
> (Open-Meteo and Overpass). If either is unreachable or rate-limited, its fields return
> `null` rather than failing the request, and pond options are then sized by terrain
> capacity alone. The catchment analysis is computed entirely from the uploaded file, so
> it is unaffected — no external service can suppress the primary result.

---

## Extensibility

### The analysis core is input-agnostic

The catchment engine takes an elevation grid and a bounding box — not a KML. The
uploaded-file path and a second path that fetches a DEM for a map click both call the same
function and return the same response shape. A new terrain source in a later phase becomes
a new parser, with no change to the analysis.

### Layers are separated by what they touch

- **`domain/`** — pure calculation: catchment delineation, runoff, pond sizing, land
  availability. No I/O, so each piece is unit-testable in isolation.
- **`infrastructure/`** — everything that talks to the outside world: KML parsing,
  rainfall, land use, elevation, caching.
- **`services/`** — orchestration across several domain functions and clients.
- **`api/`** — HTTP concerns only, with no business logic.

### Tuning values are named constants, not literals

Grid resolution, the catchment target band, candidate depths, flood-fill resolution and
sampling density are all named constants carrying the reasoning for their value.
Retargeting the tool at a different structure — a check dam rather than a farm pond — is a
constant change, not a rewrite.

### The runoff model is ready to be replaced

Runoff currently uses the rainfall-coefficient method and tags every result with the
method that produced it. The intended upgrade is SCS Curve Number, using land-cover data
the project already fetches; the tag exists so a response can say which model produced it
once both are available.

### Verification

104 backend tests cover the domain calculations, the KML and KMZ parsing paths, and the
endpoint's upload contract, including invariants that previously failed — that a pond site
must lie inside its own catchment, and that a bowl-shaped basin must report non-zero
storage.

---

## Known limitations

- **Elevation is read from the placemark name.** Each contour's height comes from its
  `<name>` parsed as a number, which matches the sample map's convention. Maps that carry
  elevation in a description, an extended data field, or the coordinate's Z value will
  need the parser extended — a contained change in one module.
- **The analysis grid is fixed at 300 × 300.** Ground resolution therefore varies with the
  size of the uploaded area. A much larger survey would be analysed more coarsely.
- **The runoff coefficient is a single constant (0.25).** It does not yet vary with soil,
  slope or land cover, and is the least defensible number in the chain.
- **Only farm-pond scale is proposed.** By design, site selection targets 1–5 ha. For a
  larger catchment the tool prefers a smaller sub-catchment rather than proposing a check
  dam.
- **One site is returned, not a ranked set.** Candidates are already scored internally, so
  returning the best three is a natural next step.
- **First request after a restart is slow.** Cold library loading and just-in-time
  compilation of the routing code make the first analysis noticeably slower than
  subsequent ones.

---

*Design decisions referenced throughout are recorded with their reasoning in
[`docs/DECISIONS.md`](DECISIONS.md).*
