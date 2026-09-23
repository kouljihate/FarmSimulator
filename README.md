# Farm Simulator — Part 1

> **Version**: 0.36.5 · repo: https://github.com/kouljihate/FarmSimulator

A bilingual (English / Arabic) desktop-web tool that turns a Google Maps
export (land boundary + water point) into a full **irrigation plan**.
It is a **single-URL SPA**: everything lives on `/` — the shell page holds
the tab bar and every interaction (upload, load, basin edits, sector ops,
config overview) is a `POST /` returning JSON, with tab bodies injected in
place. The browser never leaves `/`.

1. **Basin placement** — the best spot near the water point, favouring higher
   elevation inside the land.
2. **Sectorisation** — 3 config suggestions that split the land into sectors
   `≤ 10,000 m²` (S1, S2, …). If the uploaded file *already contains* a sector
   layout (extra polygons covering ≥ 50 % of the land), those are used directly
   and **no new suggestions are generated**.
3. **Zonage** — every sector is divided into 3 equal-area zones (Z1, Z2, Z3),
    each with its **name label shown directly on the zone map**.
   Zones are managed per sector from the **Open** modal (rename, remove, split
   by tracing a line on the map or entering X/Y start + X/Y stop) and locked
   with the **Confirm Zones** button at the end of the Zones tab — confirming
   reveals the valves.
4. **Valves** — one principal **90 mm** valve at each sector entry plus one
    secondary **32 mm** valve per zone. The Valve tab shows a large 620 px map
    with sectors + all zones (with name labels) + draggable valve markers:
    clicking a marker selects it and shows its full info (name, kind, diameter,
    sector, zone, X/Y) in the Selected-valve panel; dragging a marker
    updates the info live on release and auto-saves the move (all-sectors view).
    Sector checkbox pills multi-select the focused sectors (all/none checked =
    whole farm); a subset stages drags (amber row) until **Save** persists
    them, and switching sectors auto-saves first. A **Show rows** checkbox
    overlays the AI crop rows on the map. Below the map a
    single table lists **all** valves (principal + secondary) with an Actions
    column of circle Edit/Remove icon buttons — Edit shows the valve info,
    highlights its row and focuses its marker on the map.
    Moved valves keep their position through
    sector/zone/basin rebuilds (override layer); moved secondary valves pull
    their 63/32 mm pipes along; removed valves stay removed.
5. **Piping** — 90 mm principal pipe (basin → sector entries), **63 mm** major
   pipes (sector valve → each zone valve), 32 mm minor pipes (valve → zone
   supply point). The Pipes tab mirrors the Valve tab: sector + pipe-type
   filters (single sector zooms map + table to it; type pills filter
   principal 90 / major 63 / minor 32 / custom), large clickable map (pipe → info panel
   with type/diameter/sector/zone/length) and one unified table with a
   circle Locate button per pipe. A pipe management card adds full
   Add/Change/Remove: pick a pipe (or trace start/end on the map), set
   diameter 90/63/32 and sector/zone, then Add or Save; per-row Edit fills
   the form and focuses the pipe. Changes survive rebuilds via an override
   layer (`pipe_overrides` / `removed_pipes` / `custom_pipes`); only the
   principal pipe cannot be removed.
6. **Other Elements** — pressure reducers, connectors (90×63, 63×32), tees,
   elbows, filters, booster pumps placed on a big land map (click the map to
   fill coordinates). Every added element gets a heuristic **AI analysis**
   (necessary or not) plus a proposal for a smoother, cheaper network.
7. **Simulation** — ROI after X years (investment, annual cost/revenue, crop)
   with a yearly table, break-even year and an **AI proposal** for a
   high-income, low-headache plan.
8. **Final Result** — one map with everything (sectors, zones, valves, all
   pipes, other elements) plus a detailed land report with an **Export PDF**
   button (print).

All interactive maps use Folium + OpenStreetMap tiles. The UI is fully
bilingual: English (Comfortaa) on the left, Arabic (VIP RAWY Regular) on the
right. Tab buttons are bilingual (`bi(key)` inline helper), and
placeholder headings for future tabs (Zones, Valve, Pipes, Final Result) are
also bilingual. Config headings show Arabic translations of their base names
(Balanced grid → شبكة متوازنة; Mosaic → فسيفساء; Fine → دقيق; Existing sectors
→ قطاعات موجودة) with the count localised (cells → خلايا, polygons → مضلّعات).
Styling is **Tailwind CSS** (CDN) with a futuristic dark theme (neon
cyan/violet gradients, glassmorphism cards, glow buttons). A fixed footer of 3
equal columns shows the app name, the Part 1 tag, and the current version
 (right-aligned). The home page has a
 centred tab bar: **Load, Upload, Basin, Sectors, Zones, Rows, Valve, Pipes,
 Other Elements, Trees, Simulation, Recap, Final Result**
(the pipeline stages; last five are placeholders for future parts). The
"Accepted formats" and "What Part 1 produces"
cards split their content into two columns: English on the left, Arabic on the
right.

---

## Requirements

- Python **3.12+** (developed on 3.14)
- Dependencies (see `requirements.txt`): `flask`, `shapely`, `pyproj`, `folium`,
  `pymongo`
- A running **MongoDB** on `127.0.0.1:27017` for persistence (optional: the app
  auto-falls back to per-run pickle files in `uploads/` if MongoDB is down).
  Override with `MONGO_URI` / `MONGO_DB` env vars (defaults
  `mongodb://127.0.0.1:27017` / `farm_simulator`).

## Setup & run

```powershell
# one-time: create the virtual environment and install dependencies
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# run
.\venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:8501>.

## How to use

1. Click **New upload** and choose a `.kml` or `.csv` file.
2. A summary card appears **in the same Upload tab** with the file contents:
    land name + area, water point, basin recommendation and the configs with
    their sector counts — plus a button jumping to the Basin tab. A **File
    contents** block enumerates every element type from the upload: the land
    boundary (name + area), extra polygons (count + names + areas) and water
    points (count + coordinates). The result
    is also shown in full on the same page: the **Basin tab** gets an Upload Result card (basin info +
   full-width map), and the **Sectors tab** shows the 3 sectorisation
   suggestions as full-width stacked map cards (one column, edge-to-edge).
Each config card has a set of **sector checkboxes labelled with the actual
    sector name** (including custom renames; neon pills, same theme as the
    tabs; long names truncated with `max-w-20 truncate`).
    Checking one (or several)
    highlights the matching sector(s) in that card's map (yellow outline +
    fill), expands a **sector accordion** below with a 3-column EN / data / AR
    breakdown (name, area, centroid, entry point, zone angle, zone count), and
    clicking any sector inside the map toggles its checkbox —
    multiple sectors can stay selected at once (map-driven toggles also
    expand/collapse the matching accordion). Pills (and accordions) are always
    shown sorted by name, A-Z case-insensitive with natural numbers (S2 before
    S10), so a rename visibly re-orders the list.
3. **Manage sectors** — each config card now has a taller map and a centred
    toolbar of **rounded two-row buttons** (Arabic on top, English below):
    **Add** (draw the new sector boundary on the map, then *Done*),
    **Edit** (drag the vertices of a selected sector, then *Done*),
    **Rename**, **Merge** (check two sectors), **Swap** (check two sectors to
    exchange their names), **Remove**. The toolbar row is
    `justify-between`: **"Manage" on the left**, the tool buttons in the
    middle, **"إدارة" on the right** — there is no separate status line;
    selection/merge guidance is shown in the top error banner (sourced from a
    hidden `#sector-i18n` store holding the `ts()` bilingual strings, so the
    Add/Edit **Done** label keeps working). Every failed request (missing
    token, HTTP/network error, bad payload) now surfaces a bilingual message
    in the top error banner instead of failing silently. **Rename** and
   **Remove** ask for confirmation in a small modal dialog — the modal header
   shows bilingual text (English left, Arabic right), the body and buttons
   show Arabic on top and English below. The modal matches the app theme
   (blurred backdrop, glassmorphism card with neon glow, gradient
    confirm/danger buttons). **Removing (or merging/editing) a sector does not
    rename the others** — the remaining sectors keep their names (S3 stays S3,
    custom names stay); adding a new sector picks the next free `S{max+1}`
    name.     **Sector names must be unique**: renaming to an already-used name
    (case-insensitive) is rejected with a bilingual error, as are empty names.
    Any other name is accepted — including `S<number>`-style names. Every edit rebuilds
    the sector chain, zones, valves and piping for that config and re-renders
    its map in place (`POST /` `{op:sector_coords}` / `{op:sector_action}`);
    the result is persisted so a reload keeps it.
4. Pick a config with **Use this config** → its detail loads **in the same
     page** (no navigation): the **Zones** tab shows per-sector maps with zones
     only (no valves, no pipes yet), the **Rows** tab traces AI crop rows per
     zone along elevation contours (direction, slope, count, length + spacing
     control), the **Valve** tab shows the valves map
     (principal 90 mm + secondary 32 mm lists), the **Pipes** tab shows the
     piping map (90 / 63 / 32 mm), **Other Elements** shows the big editable
     network map, the **Trees** tab assigns a tree type per zone (mixed
     allowed), **Simulation** shows the ROI planner, the **Recap** tab shows a
     big map of every component with per-layer show/color/size controls, and
     **Final Result**
     shows the full map + legend + report with PDF export.
     Every Zones card has an **Open** button that launches a modal with a large
     map of that sector and its zones plus its zone table — with **zone
     management built in**: rename / remove a zone, or split a zone by
     tracing a line on the map (**Trace on map**, two clicks fill X/Y
     start/stop) or by typing the coordinates, then **Split**. Sector
     Add/Edit/Rename/Remove actions are still available from the same modal.
     Press **Confirm Zones** at the bottom of the Zones tab to lock the
     layout and reveal the valves.
5. Every run is persisted — plan + all generated maps (basin, config
   previews, overviews, per-sector, other-elements) — into MongoDB (or `uploads/<token>.db`
   pickles as fallback), **saved again on every step** (upload, basin Apply,
   sector/zone edits, confirm, other elements, simulation). Storage is keyed
   by **land name (unique)**: re-uploading the same land reuses its record
   instead of creating a duplicate, and the **Load** tab shows **one row per
   land** (name + last-save date `Last saved: YYYY-MM-DD HH:MM` on the same
   row, newest first) with **Load** and **Delete** (removes the whole land)
   buttons; one click restores the complete page with the saved maps
   (`POST /` `{op:load}`). DB layout per land:
   `{Land: [Basin], [Sectors, [Zones, [Valves], [Pipes]]]}` plus other
   elements and the simulation.
6. **Move the basin**: in the Basin tab, drag the brown marker or edit X/Y
    (longitude/latitude) — both stay in sync live. Press **Apply** to save:
    `POST /` `{op:basin}` re-runs sector ordering, zones, valves and piping and
    updates the Basin map (via the `srcdoc` attribute) and the **Sectors** maps
    in place, without reloading the page. An open config overview is
    silently re-fetched so Zones/Valve/Pipes/Final stay in sync.

### Accepted file formats

- **KML** (Google My Maps export):
  - polygon `Placemark`(s) = land boundary (the one containing the water
    point, or the largest) + optional altitude `z` per vertex (used to pick a
    high basin spot);
  - a `Point` `Placemark` = the water source;
  - the `description` field acts as the element **type** (same keywords as the
    CSV `type` column: `water`, `point`, `source`, `puit`, `valve` → water;
    boundary words like `boundary`, `parcel`, `parcelle`, `terrain` → land):
    a water-described polygon contributes its centre as a water point, and a
    land-described point is skipped as a mere label. Placemarks without a
    description keep the default rule (polygons = boundaries, points = water);
  - extra polygons covering ≥ 50 % of the land are interpreted as an
    *existing sector layout* and used as-is: each polygon stays its own
    sector, grouped and ordered by `description` (sectors named
    `<description> <k>` per group, e.g. `North 1`, `North 2`).
- **CSV/TXT**, header row with any of:
  - coordinates: `lat` / `lon` (also `lng`, `long`, `longitude`);
  - a `type` column where rows marked `water` (or `point`, `source`, `puit`,
    `valve`) are the water source;
  - a WKT column (`wkt` / `polygon` / `geometry`) is also supported — quoted
    cells with commas are handled.

The samples folder contains `test_parcel.kml` (≈ 46 019 m² parcel with fake
terrain) and its generator `make_test_kml.py`.

## Project layout

```
app.py                     single-URL SPA backend: GET / shell, POST / JSON ops
                           (upload/load/list_runs/delete_run/basin/sector_coords/sector_action/
                            zone_action/valve_action/overview/other_add/other_remove/sim_save)
core/
  geo.py                   UTM projector, affine helpers, sweep_split, main axis
  parser.py                KML / CSV / WKT parsing
  engine.py                pipeline: basin, sectorise, zones, valves, pipes + sector ops
                 (apply_sector_op / recompute_sectors: rename, remove, merge, add, edit)
                  + zone ops (apply_zone_op: rename, remove, split, swap, merge, confirm),
                 other-element AI analysis, ROI simulation + AI proposal
  sector.py                smart recursive area-balanced sector partitioner
  mapper.py                folium map recipes (bilingual tooltips)
  storage.py               MongoStore / FileStore (get_store()); saves plan + all maps
  i18n.py                  EN/AR dictionaries + t/bt/btcfg/css helpers
templates/                 base, index (SPA shell) + partials: _basin_result,
                           _sectors_result, _zones_result, _valves_result,
                           _pipes_result, _other_result, _simulation_result,
                           _final_result (Tailwind CSS CDN)
static/fonts/              VIP RAWY REGULAR REGULAR.TTF (Arabic)
samples/                   test KML + generator
uploads/                   runtime: uploaded raw files (+ <token>.db pickle fallback)
```

## Persistence

- `core/storage.get_store()` returns a `MongoStore` when MongoDB is reachable,
  otherwise a `FileStore` (per-token pickles in `uploads/<token>.db`; old
  `<token>.pkl` files are migrated on read).
- Every stored record holds `name`, `updated_at`, `plan` (pickled) plus
  `basin_map`, `cfg_maps`, `overview_maps`, `sector_maps`, `other_maps`
  (per-config keys are stringified for BSON). Ops persist at upload, on basin
  **Apply**, on sector/zone actions, on confirm, and when overview/other/
  simulation data is generated (maps are also reused instead of recomputed
  once saved). Records are keyed by land name: re-uploading the same land
  overwrites its record, `list_runs` is deduplicated to one row per land, and
  `delete_run` removes the whole land. The web UI lists/loads/deletes runs via
  the **Load** tab (`POST /` `{op:list_runs}` / `{op:load}` /
  `{op:delete_run}`).

## Single-URL SPA

- The browser only ever uses `/`: `GET /` serves the shell (tab bar + empty
  panels + saved-runs list); every interaction is a `POST /` — multipart with
  a file for upload, otherwise JSON `{op, …}` — returning fragments and/or
  plain-data summaries that the tab JS injects in place.
- `plan_summary()` strips shapely objects down to JSON-safe dicts for the
  client state; map HTML travels as strings (`basin_map`, per-config previews,
  overview + per-sector + other-elements maps).

## Architecture notes

- All geometry work is done in **projected (UTM) metres** via
  `core.geo.Projector`; only final display coordinates are lon/lat.
- `engine.analyse(parsed)` returns a `plan` dict; `engine.extend(plan, cfgid)`
  lazily computes zones/valves/pipes for a chosen config.
- Sectorisation is deterministic and produces compact, near-square cells:
  `core/sector.partition` recursively splits the largest cell along its longest
  local axis at a controlled area fraction and folds away slivers
  (< 0.4 % of the parent area).
- Config/sector/zone schema used across templates and mappers — see
  `PROMPT.md` for the full data model.

## Data model (summary)

| Object | Keys |
| --- | --- |
| `plan` | `name, all_boundaries, boundaries[{name,description,is_land,area_m2}], water_points[{lon,lat}], n_water_points, land, land_area_m2, water, basin, basin_m, max_elev_m, configs, existing_sectors, other_elements[{id,kind,lon,lat,size,note,necessary,verdict,suggestion}], simulation{years,capex,annual_cost,annual_revenue,crop}, _proj, _basin_m, _land_m` |
| `config` | `id, name, angle, n_sectors, sectors, ready, zones_confirmed, rows_confirmed, valve_overrides{(kind,sector,zone):[lon,lat]}, removed_valves[], custom_valves[]` + post-extend `zones, valves, pipes` |
| `sector` | `idx, name, poly_m, poly, centroid, area_m2, entry, entry_m, zone_angle` |
| `valve` | principal: `{id:P:<sector>, kind:principal, sector, diameter_mm:90, lon, lat, point, name}`; secondary: `{id:S:<zone>, kind:secondary, sector, zone, diameter_mm:32, lon, lat, point, name}` (+ `moved` when repositioned, `custom:true` for added valves) |
| `pipes` | `principal({diameter_mm:90,…}), majors[]({zone, sector, diameter_mm:63, len_m}), minors[]({zone, sector, diameter_mm:32, len_m})` |
