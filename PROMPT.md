# PROMPT — Handoff for another AI agent

You are continuing work on **Farm Simulator — Part 1**, a bilingual Flask web
app at `D:\Projects\opencode\FarmSimulator` (Windows, PowerShell 5.1 is the
shell; do **not** use `&&` — chain with `;` / `if ($?) { }`).

Read `README.md` first. Below is the exact state of the code and the rules you
must preserve.

## How to run and verify

```powershell
cd D:\Projects\opencode\FarmSimulator
.\venv\Scripts\python.exe app.py        # -> http://127.0.0.1:8501
```

Verify without the browser (use this every time you touch engine/parser/mapper):

```powershell
.\venv\Scripts\python.exe -X utf8 -c "from core import engine, parser; p=parser.load_file('samples/test_parcel.kml'); plan=engine.analyse(p); [print(c['name'], [round(s['area_m2'],1) for s in c['sectors']]) for c in plan['configs']]; engine.extend(plan,0); print('valves', len(plan['configs'][0]['valves']))"
```

Expected: **exactly 3 configs**, every sector `≤ 10000 m²`, each config total
`≈ 46019 m²`, and `engine.extend` yields 3 balanced zones per sector.

Route smoke test (all must be 200): `POST /upload` → `GET /view/<token>/<cfgid>`
→ `GET /sector/<token>/<cfgid>/<sidx>`; unknown token must 404.

## Current state (all verified working)

- Part 1 pipeline complete: basin → sectorisation → 3 zones/sector → 50 mm
  valves → 90/50/32 mm piping.
- Sectorisation is **deterministic and smart**: `core/sector.py` "land-and-water
  kd-tree" recursively splits the largest cell along its longest local axis at
  controlled area fractions; slivers `< 0.4 %` of parent area are folded into
  the nearest neighbour; holes/concave land preserved via affine+box clipping;
  `make_valid` repairs numeric artefacts.
- `core/engine.py` `_sector_defs()` now returns **3 suggestions** (was 5):
  Balanced grid, Mosaic (mixed sizes), Fine (smaller cells).
- **Existing-sector detection** (requirement 3): if the upload contains extra
  polygons that (a) intersect the land ≥ 50 % of their own area, (b) are
  `≥ 100 m²`, and (c) jointly cover `≥ 50 %` of the land, they are used as the
  sectors directly (`_existing_config`, config named `Existing sectors (N
  polygons)`), and `plan['existing_sectors']=True`. No suggestions are built.
  The home page then shows the "EXISTING_TITLE/SUB" heading (inside the
  Upload Result card).
- **Maps are OSM-only** (requirement 1): `core/mapper.py` `_render_base` uses
  `tiles="OpenStreetMap"`, no satellite tiles, no `LayerControl`. There must be
  zero `ArcGIS` / satellite / layer-control strings in map output.
- Persistence: `core/storage.get_store()` returns a **`MongoStore`** when
  MongoDB (`127.0.0.1:27017`; env overrides `MONGO_URI`/`MONGO_DB`, default db
  `farm_simulator`, collection `plans`) is reachable, else a **`FileStore`**
  (per-token pickles in `uploads/<token>.db`; legacy `uploads/<token>.pkl`
  files are migrated to the store on read). API: `get_plan`, `load`,
  `save(token, plan, maps)`, `save_maps(token, maps)`, `list_runs(limit)`.
  A stored record holds `name`, `updated_at`, `plan` (pickled Binary) and the
  maps `basin_map`, `cfg_maps`, `overview_maps`, `sector_maps` — per-config
  dict keys are **stringified for BSON and cast back to int on read**
  (`_encode`/`_decode`). Routes persist at `/upload`, on basin **Apply**
  (`edit_basin`), and in `view_config`/`sector_detail` (overview + per-sector
  maps are **reused from the store instead of recomputed** once saved).
  The **Load** tab (first tab, `tab-load`) lists saved runs
  (`context_processor` injects `runs=STORE.list_runs()`), and
  `GET /load/<token>` restores a full page from the saved plan + saved maps
  (recomputes only if missing). i18n keys: `LOAD_TITLE`, `LOAD`, `LOAD_EMPTY`
  (EN+AR).
- `/upload` re-renders `index.html` (same page). The **Basin tab** holds an
  **"Upload Result" card** (`UPLOAD_RESULT_TITLE`, id `upload-result-card`,
  header with no version) whose content lives in `templates/_basin_result.html`:
  plan summary row, then a **Basin placement** card split into **2 columns on
  lg**: left column = info texts (row 1) + full-width basin map (row 2); right
  column = the X/Y lon/lat inputs + **Apply** button panel that spans the full
  height of both rows (vertically centred). The **Sectors tab**
holds `templates/_sectors_result.html` (sectorisation heading + config map
   cards + legend); `result.html` / `_upload_result.html` were removed.
   In the **Sectorisation card the config cards are single-column full-width**
   (`grid-cols-1`, maps bleed edge-to-edge via `-mx-6`), stacked vertically.
   Each config card shows **sector checkboxes** (`sector-check` label +
   hidden `sector-chk` input, `data-cfg`/`data-idx`, name in `value`)
   grouped across one row (`flex-wrap justify-center`), neon themed, labelled
   **just `S1`, `S2`, …** (the native checkbox square is `display:none`;
   a checked pill glows via `.sector-check:has(.sector-chk:checked)`).
   **Multiple boxes can be checked at once**; all checked sectors are
   highlighted in the map, and clicking a sector *in* the map toggles its
   checkbox. The toolbar (`tool-btn`, rounded, two stacked lines via
   `bv(key)` = Arabic on top + English below; `ts(key)` feeds plain bilingual
   `data-t*` status texts) holds Add/Edit/Rename/Merge/Remove. The preview
   maps are interactive, built by `mapper._sector_select_js(cfg)`: sector
   polygons are drawn directly with Leaflet (a `sector` option tags each;
   folium drops unknown options) and carry a `sticky` tooltip;
   `window.selectSectors([...])` syncs the highlighted set from the parent
   checkboxes, `window.toggleSector(idx)` flips one (used by map clicks, which
   post `{type:'sector-select', cfg, idx, checked}` to `window.top`), and a
   single-select `window.selectSector(idx)` is kept for legacy checks.
   `index.html` listens for `change` on `.sector-chk`, tracks the last-checked
   sector as the operation target (`sel[cfg]`; merge uses **any two checked
   sectors**), and descends the map iframe (outer srcdoc → inner folium
   iframe) to call `selectSectors`, polling until the map is ready.
   `load_run` regenerates config preview maps that lack `selectSector`
   (old saved runs). i18n: `SECTOR_SELECT`, `SECTOR_SELECT_MULTI` (EN+AR).
- **Sector management** (v0.8.0): each config card has a **taller map**
   (`iframe.map.tall`, 560 px) and a toolbar of `tool-btn` buttons with
   `data-op` = `add | edit | rename | merge | remove` plus a status line.
   `core/engine.py` exposes `apply_sector_op(plan, cfg, op, idx, idx2, name,
   ring)` → rebuilds the sector chain/entries via `recompute_sectors` (re-sorts
   by distance to basin, keeps custom non-`S\d+` names) and the full
   zones/valves/pipes pipeline. Rules: rename rejects `S<digits>` only; remove
   needs ≥ 2 sectors; add/edit need a valid ring inside the land (≥ 90 % of
   area, ≥ 60 m²) — add **carves** the new polygon out of every existing sector
   (`difference`); merge unions two sectors keeping the first's name.
   `core/mapper._sector_manage_js(cfg)` adds draw/edit tools (`startDraw`,
   `startEdit(idx, ring)` that rewires vertex drags, `finishDraw/finishEdit`,
   Escape = cancel) posting `sector-draw` / `sector-edit` / `sector-cancel`
   (+ `sector-draw-start` / `sector-edit-start`) to `window.top`.
   Routes: `GET /sectors/<token>/<cfgid>/<idx>/coords` (returns the closed
   ring) and `POST /sectors/<token>/<cfgid>/action` (JSON `{action, idx, idx2,
   name, ring}`) → applies the op, regenerates `cfg_maps`, persists via
   `STORE.save`, clears the stale `overview_maps`/`sector_maps` for that cfg,
   returns `{ok, error?, sectors}` (the `_sectors_result.html` fragment
   `index.html` swaps into `#sectors-result`). Draw flow in the live map is
   Leaflet `L.Polygon` with editable-drag vertices (dash-array guides).
   `sweep_split` in `core/geo.py` now coalesces slivers so pieces are pure
   (Multi)Polygons (folium/neumann: GeometryCollection pieces had `.boundary =
   None` and crashed `nearest_points` in `extend_config`).
   i18n keys (EN+AR): `MANAGE, SECTOR_ADD, SECTOR_EDIT, SECTOR_RENAME,
   SECTOR_MERGE, SECTOR_REMOVE, SELECT_HINT, SELECT_NEEDED, MERGE_PICK,
   DRAW_HINT, EDIT_HINT, FINISH, CANCEL, SECTOR_NEEDS_NAME, SECTOR_RENAMED,
   SAVING, MERGED_OK, REMOVED_OK, ADDED_OK, EDITED_OK`.
  The **Basin placement card body is split 80% / 20%** on lg
  (`lg:grid-cols-[4fr_1fr]`): first column = info grid + basin map, second
  column = the X/Y + Apply form.
- Default active tab: **Upload** when no result card exists, **Basin** once a
  plan was analysed (`upload-result-card` is present).
- Bilingual: English left (Comfortaa), Arabic right (VIP RAWY Regular in
  `static/fonts/`). Text goes through `core/i18n.py` helpers registered as
  Jinja globals in `app.py`: `t`, `bt`, `btcfg`, `i18n_css`. Map tooltips use
  inline-styled spans via `i18n.bl_style/map_tip`. Errors via `i18n.err(msg)`
  (automatically chooses EN/AR). Templates: `base/index/result/config/sector`,
  Bootswatch Flatly CDN.

- Templared with **Tailwind CSS** (CDN in `base.html`) with a **futuristic dark
  theme**: neon cyan/violet/fuchsia gradients, glassmorphism cards (`.glass`),
  gradient glow buttons (`.glow-btn`), grid + radial background, Comfortaa (EN)
  + VIP RAWY Regular (AR) fonts — one `tailwind.config` block, fonts kept as-is.
  `.glass`/`.glass-head` are reserved for chrome (navbar, shared outer card,
  footer); **every tab content card** uses the flat Upload-tab style
  `rounded-2xl border border-white/10 bg-white/5` with
  `border-b border-white/10 px-5 py-3` headers — applied uniformly in all tabs.
- Home page has a **centred pill tab bar**: **Load, Upload, Basin, Sectors,
  Zones, Valve, Pipes, Final Result** (pipeline stages; placeholders that show
  `t('UPLOAD_FIRST')` = "Upload First a File (csv/kml)" when nothing was
  uploaded yet).
  Tab switching is a small vanilla-JS snippet in `index.html`; styles live in
  `base.html` (`.tab-btn`, `.tab-panel`). Default (active) tab: **Upload**
  when no result card exists, **Basin** once a plan was analysed
  (`#upload-result-card` is present).
  The "Analyse the plot" button is wider than its card (`-mx-6` bleed).
- "Accepted formats" and "What Part 1 produces" cards render the body as **two
  columns: English left, Arabic right** (via `tl(key)` = `(en, ar)` plain-text
  pairs; Arabic column is `dir=rtl` with the VIP RAWY family).
- Home header shows only the bilingual app name: **Farm Simulator** (left) +
  **محاكي المزرعة** (right). Browser tab title carries the Part 1 title
  (`Farm Simulator - Part 1 - irrigation network`).
- A **fixed footer** (3 equal columns) shows the app name (left), the Part 1
  tag (centre, bilingual) and the version (right-aligned). The version comes
  from the `VERSION` file via the `version` Jinja global (`app.py`).
- Arabic font sizes are fixed in `i18n.css`: **20 px** for titles (h1..h5
  Arabic), **18 px** for card headers (`.glass-head`) and for button/link
  Arabic, **16 px** for every other Arabic element. The navbar Arabic brand is
  20 px (`text-xl`).

## Delivery workflow — do this on EVERY prompt

1. Bump `VERSION` (patch for small fixes, minor for features, e.g. `0.1.0` →
   `0.2.0`).
2. Update `README.md` and this `PROMPT.md` to match the new behaviour.
3. Commit and push to **`kouljihate/FarmSimulator`** (repo is git; `gh` is
   authenticated as `kouljihate`). Use:
   ```powershell
   git add -A; git commit -m "<short message>"; git push origin main
   ```
   Create the repo first if missing: `gh repo create FarmSimulator --source=. --public --push`.

## Data model (exact keys — do not rename without updating templates + mappers)

`plan`:
`name, all_boundaries[{name,poly,is_land}], land (Polygon ll), land_area_m2,
water{lon,lat}, basin{lon,lat,z,has_elev,max_elev,dist_water_m}, basin_m,
max_elev_m, configs[], existing_sectors(bool), _proj (Projector), _basin_m,
_land_m`

`config`: `id, name, angle, n_sectors, sectors[], ready` and after
`engine.extend(plan, cid)`: `zones[], valves[], pipes`
(`pipes = {principal:{diameter_mm:90, line, len_m},
            majors:[{zone,diameter_mm:50,line,len_m}],
            minors:[{zone,diameter_mm:32,line,len_m}]}`)

Basin editing: `engine.set_basin(plan, lon, lat)` validates the point is
inside the land (`_land_m.distance(pt) <= 1.0`), updates `basin`,
`_basin_m`/`basin_m`, recomputes `dist_water_m` and re-runs `sectorise` /
`_existing_config` (entries/ordering + zones/pipes then come from the new
point). Route `POST /basin/<token>` (`app.py edit_basin`) accepts a plain form
POST (full re-render) or an AJAX call (`X-Requested-With: XMLHttpRequest`;
returns JSON `{ok, error_html, basin{lon,lat,dist_water_m}, basin_map,
sectors(_sectors_result.html fragment)}`). `index.html` then swaps the
`#basin-map-frame` srcdoc and `#sectors-result` innerHTML in place. The Basin
map adds a **draggable** folium `Marker` and `mapper._drag_js` (injected via
`folium.Element`) which exposes `window.basinSet(lon, lat)` (parent calls it
from the X/Y inputs' `input` events) and, on `dragend`, posts
`{type:'basin-marker-drag', lon, lat}` to `window.top` (the map sits one extra
folium iframe deep); the parent message listener just fills the X/Y inputs
(no auto-submit — Apply triggers the save). i18n keys for the editor: `APPLY`, `LON`, `LAT`, `DRAG_HINT`,
plus the `"Point is outside the land boundary."` error.

`sector`: `idx (1-based), name (S{idx}), poly_m, poly (lonlat), centroid,
area_m2, entry, entry_m, zone_angle` (+ post-extend `zones[]`)

`zone`: `idx (1-based), name (S1-Z1…), poly_m, poly, area_m2, centroid`

`valve`: `zone, diameter_mm:50, lon, lat, point, name`

## Conventions and constraints

- All geometry math happens in projected UTM metres (`core.geo.Projector`,
  `to_m` / `to_lonlat`). Never do area/centre computations in lon/lat.
- **No comments in code unless asked.** Follow existing style (module docstrings
  are fine and present).
- Determinism matters: same input → same output (stable orderings, no RNG).
- Do not introduce new heavy dependencies without a good reason; if you do,
  update `requirements.txt` (currently flask, shapely, pyproj, folium, pymongo)
  and note it.
- Python 3.14 venv in `.\venv\`. Prefer test-client requests over `requests`
  lib (not installed).
- `README.md` and this `PROMPT.md` must be kept in sync with behaviour changes.

## Next planned work (Part 2)

Not started. Likely scope: crops / trees, or additional irrigation objects.
Confirm with the user before designing anything — and keep all new text
bilingual (add EN+AR keys to `core/i18n.py`).

## Recent history (so you can answer "what did we do so far")

1. Built part-1 pipeline + bilingual UI, fixed parser bugs (KML Z handling,
   WKT CSV comma-split rejoin, UnboundLocalError) and the restart-404
   (disk persistence of plans).
2. Replaced naive slicing with the smart partitioner (`core/sector.py`) +
   per-sector `zone_angle`.
3. Three latest changes: OSM-only maps; exactly 3 suggestions; existing
   sectors in the upload are reused instead of generating new ones.
4. v0.6.x: result moved into the Basin tab with an editable basin (draggable
   marker + X/Y inputs in live sync, AJAX Apply), sectors in the Sectors tab,
   unified flat theme, `UPLOAD_FIRST` placeholders, 80/20 basin card layout.
5. v0.7.0: **MongoDB persistence** (`core/storage.py`), all maps saved with
   the plan, new **Load** tab (first) to list and restore saved runs.
6. v0.7.1: Sectors tab config cards made single-column full-width maps.
7. v0.7.2: sector circle buttons select sectors in the config maps (click a
   chip → highlight in map; click a sector in map → activate its chip).
8. v0.7.3: sector buttons spread on one row (`justify-between`) with the neon
   theme.
9. v0.8.0: **full sector management** — Add (draw), Edit (drag vertices),
   Rename, Merge, Remove per config, all rebuilding the pipeline and maps
   in place (AJAX fragment swap), with taller maps; fixed a `sweep_split`
   crash on GeometryCollection zone pieces.
10. v0.9.0: sector circle buttons replaced with **grouped checkboxes**
   (`sector-check`/`sector-chk`); multiple sectors can be checked/highlighted
   at once, map clicks toggle checkboxes, and Merge uses any two checked
   sectors.
11. v0.9.1: checkbox pills now show only the name (`S1`), and the sector
   tools are rounded two-row buttons (Arabic on top, English below) via the
   new `bv`/`ts` i18n helpers; button labels are captured in JS at arm time
   (no more server `data-label` markup).
12. v0.9.2: **Rename** and **Remove** now open a small in-page modal
   (`#sector-modal` in `index.html`) instead of `prompt()`/`confirm()` —
   rename has a new-name input, remove shows a "cannot be undone" message;
   both confirm/cancel/Enter/Escape/backdrop-click. New i18n keys
   `CONFIRM`, `NEW_NAME`, `REMOVE_ASK` + the `tsf(key, **kw)` helper.
13. v0.9.3: checkbox labels are **strictly sequential `S1`, `S2`, …** (every
   sector shown, label = `"S" + loop.index`, actual name kept in `value` +
   plain `title`); fixed malformed bilingual-markup `title`/`data-*`
   attributes (must use `ts()`/`tsf()` plain helpers, set via
   `textContent`, never `t()` markup inside attribute values).
14. v0.9.4: the rename/remove modal got the app theme — blurred backdrop,
   `sector-modal-card` glass card with radial neon gradients + glow, neon
   input focus, `sector-modal-btn` gradient buttons (`.primary` cyan/violet
   for confirm-rename, `.danger` red for remove). JS now sets
   `modalOk.className = 'sector-modal-btn primary|danger'`.
15. v0.9.5: **remove/merge/edit no longer renumber the other sectors** —
   `recompute_sectors` keeps every existing name as-is (only a brand-new
   sector gets a name: the next free `S{max+1}` via `_sector_num`, avoiding
   duplicates after preserved-names edits).