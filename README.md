# Farm Simulator — Part 1

> **Version**: 0.8.0 · repo: https://github.com/kouljihate/FarmSimulator

A bilingual (English / Arabic) desktop-web tool that turns a Google Maps
export (land boundary + water point) into a full **irrigation plan**:

1. **Basin placement** — the best spot near the water point, favouring higher
   elevation inside the land.
2. **Sectorisation** — 3 config suggestions that split the land into sectors
   `≤ 10,000 m²` (S1, S2, …). If the uploaded file *already contains* a sector
   layout (extra polygons covering ≥ 50 % of the land), those are used directly
   and **no new suggestions are generated**.
3. **Zonage** — every sector is divided into 3 equal-area zones (Z1, Z2, Z3).
4. **Valves** — one 50 mm valve at the entry of each zone.
5. **Piping** — 90 mm principal pipe (basin → sector entries), 50 mm major
   pipes (principal → each valve), 32 mm minor pipes (valve → zone supply
   point).

All interactive maps use Folium + OpenStreetMap tiles. The UI is fully
bilingual: English (Comfortaa) on the left, Arabic (VIP RAWY Regular) on the
right. Styling is **Tailwind CSS** (CDN) with a futuristic dark theme (neon
cyan/violet gradients, glassmorphism cards, glow buttons). A fixed footer of 3
equal columns shows the app name, the Part 1 tag, and the current version
(right-aligned). The home page has a
centred tab bar: **Load, Upload, Basin, Sectors, Zones, Valve, Pipes,
Final Result**
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
2. The app parses the land boundary and water point, then shows the result on
   the same page: the **Basin tab** gets an Upload Result card (basin info +
   full-width map), and the **Sectors tab** shows the 3 sectorisation
   suggestions as full-width stacked map cards (one column, edge-to-edge).
Each config card has a set of **circular sector buttons** (S1, S2, …)
    spread evenly across one row (neon theme, same as the tab/card styling):
    clicking one highlights the matching sector in that card's map (yellow
    outline + fill), and clicking a sector inside the map activates its button
    too.
3. **Manage sectors** — each config card now has a taller map and a toolbar:
   **Add** (draw the new sector boundary on the map, then *Done*),
   **Edit** (drag the vertices of a selected sector, then *Done*),
   **Rename**, **Merge** (pick two sectors), **Remove**. Every edit rebuilds
   the sector chain, zones, valves and piping for that config and re-renders
   its map in place (`GET /sectors/<token>/<cfgid>/<idx>/coords`,
   `POST /sectors/<token>/<cfgid>/action`); the result is persisted so a
   reload keeps it.
4. Pick a config → you get the overview with zones, valves and pipes, plus a
   page per sector.
5. Every run is persisted — plan + all generated maps (basin, config
   previews, overviews, per-sector) — into MongoDB (or `uploads/<token>.db`
   pickles as fallback). **Recover a past run** from the **Load** tab (first
   tab): it lists the saved name + token, and one click restores the complete
   page with the saved maps (`GET /load/<token>`).
6. **Move the basin**: in the Basin tab, drag the brown marker or edit X/Y
   (longitude/latitude) — both stay in sync live. Press **Apply** to save:
   `POST /basin/<token>` re-runs sector ordering, zones, valves and piping and,
   via an AJAX response, updates the Basin map and the **Sectors** maps
   in place, without reloading the page (falls back to a full render for
   non-JS clients).

### Accepted file formats

- **KML** (Google My Maps export):
  - polygon `Placemark`(s) = land boundary (the one containing the water
    point, or the largest) + optional altitude `z` per vertex (used to pick a
    high basin spot);
  - a `Point` `Placemark` = the water source;
  - extra polygons covering ≥ 50 % of the land are interpreted as an
    *existing sector layout* and used as-is.
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
app.py                     Flask routes; persistence via core/storage (MongoDB, pickle fallback)
core/
  geo.py                   UTM projector, affine helpers, sweep_split, main axis
  parser.py                KML / CSV / WKT parsing
  engine.py                pipeline: basin, sectorise, zones, valves, pipes + sector ops
                 (apply_sector_op / recompute_sectors: rename, remove, merge, add, edit)
  sector.py                smart recursive area-balanced sector partitioner
  mapper.py                folium map recipes (bilingual tooltips)
  storage.py               MongoStore / FileStore (get_store()); saves plan + all maps
  i18n.py                  EN/AR dictionaries + t/bt/btcfg/css helpers
templates/                 base, index (+ _upload_result partial), config, sector (Tailwind CSS CDN)
static/fonts/              VIP RAWY REGULAR REGULAR.TTF (Arabic)
samples/                   test KML + generator
uploads/                   runtime: uploaded raw files (+ <token>.db pickle fallback)
```

## Persistence

- `core/storage.get_store()` returns a `MongoStore` when MongoDB is reachable,
  otherwise a `FileStore` (per-token pickles in `uploads/<token>.db`; old
  `<token>.pkl` files are migrated on read).
- Every stored record holds `name`, `updated_at`, `plan` (pickled) plus
  `basin_map`, `cfg_maps`, `overview_maps`, `sector_maps` (per-config keys are
  stringified for BSON). Routes persist at upload, on basin **Apply**, and when
  overview/sector maps are generated (they are also reused instead of
  recomputed once saved). The web UI lists/loads runs via the **Load** tab
  (`GET /load`, `GET /load/<token>`).

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
| `plan` | `name, all_boundaries, land, land_area_m2, water, basin, basin_m, max_elev_m, configs, existing_sectors, _proj, _basin_m, _land_m` |
| `config` | `id, name, angle, n_sectors, sectors, ready` + post-extend `zones, valves, pipes` |
| `sector` | `idx, name, poly_m, poly, centroid, area_m2, entry, entry_m, zone_angle` |
| `pipes` | `principal({diameter_mm:90,…}), majors[]({zone, diameter_mm:50, len_m}), minors[]({zone, diameter_mm:32, len_m})` |
