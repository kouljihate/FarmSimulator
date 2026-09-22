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

Verify without the browser (use this every time you touch engine/parser/mapper/app):

```powershell
.\venv\Scripts\python.exe -X utf8 -c "from core import engine, parser; p=parser.load_file('samples/test_parcel.kml'); plan=engine.analyse(p); [print(c['name'], [round(s['area_m2'],1) for s in c['sectors']]) for c in plan['configs']]; engine.extend(plan,0); print('valves', len(plan['configs'][0]['valves']))"
```

Expected: **exactly 3 configs**, every sector `≤ 10000 m²`, each config total
`≈ 46019 m²`, and `engine.extend` yields 3 balanced zones per sector with
**principal 90 mm + secondary 32 mm valves** and **90/63/32 mm pipes**.

Route smoke test (single URL — all `POST /`, all must be 200 with `ok:true`):
upload (multipart `file`) → `{op:list_runs}` → `{op:load}` → `{op:basin}` →
`{op:sector_action}` (rename) → `{op:sector_coords}` → `{op:overview}`
(returns `zones/valves/pipes/other/sim/final_html`) → `{op:zone_action}`
(confirm/rename/split) → `{op:other_add}` → `{op:sim_save}` →
`{op:other_remove}`; unknown token/op and `{op:delete_run}` on a missing
token must return `ok:false`.

## Current state (all verified working)

- Part 1 pipeline complete: basin → sectorisation → 3 zones/sector → 50 mm
  valves → 90/50/32 mm piping.
  (v0.17.0 changed this: **principal 90 mm valve per sector + secondary
  32 mm valve per zone**, piping **90/63/32 mm** — see history §35.)
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
  `save(token, plan, maps)`, `save_maps(token, maps)`, `delete(token)`,
  `list_runs(limit)` (newest-first in both stores). A stored record holds
  `name`, `updated_at`, `plan` (pickled Binary) and the
  maps `basin_map`, `cfg_maps`, `overview_maps`, `sector_maps`, `other_maps`
  (+ `maps_v`; per-config dict keys are **stringified for BSON and cast back
  to int on read** (`_encode`/`_decode`)). Ops persist at upload/load, on basin
  **Apply** (`op:basin`), on sector actions, on zone actions, and when
  overview/sector/other maps are generated (they are **reused from the store
  instead of recomputed** once saved).
  Storage is **keyed by land name (unique, v0.17.0)**: `app._token_for_land`
  reuses the existing token when the same land is re-uploaded (overwrite, no
  duplicate), `app._dedup_runs` collapses `list_runs` to **one row per land**
  (newest wins), `{op:delete_run}` removes the whole land, and every step
  (upload, basin, sector/zone ops, confirm, other elements, simulation)
  re-saves via `app._persist`. DB layout per land:
  `{Land: [Basin], [Sectors, [Zones, [Valves], [Pipes]]]}` (+ `other_elements`,
  `simulation`). The **Load** tab (first tab, `tab-load`) lists one row per
  saved land with land name + last-save date (`SAVED_AT` + `updated_str`,
  pre-formatted server-side; `fmt_dt` Jinja global for the initial rows, same
  row as the buttons), and loading restores
  Basin+Sectors tabs from the saved plan + saved maps
  (recomputes only if missing). Each row has **Load** + **Delete** buttons
  (`data-load-token` / `data-del-token`; `refreshRuns` rebuilds both).
  i18n keys: `LOAD_TITLE`, `LOAD`, `DELETE`, `LOAD_EMPTY`,
  `SAVED_AT` (EN+AR).
- **Single-URL SPA (v0.11.0, extended v0.17.0): the browser only uses `/`.**
  `GET /` renders the `index.html` shell (tab bar, upload form, empty panels,
  runs list). Everything else is `POST /`: multipart `file` = upload;
   otherwise JSON `{op, …}` with `op` in `load | list_runs | delete_run |
   basin | sector_coords | sector_action | zone_action | valve_action |
   overview | other_add | other_remove | sim_save`. Responses carry server-rendered
  fragments (`basin_html`, `sectors_html`, `zones/valves/pipes/other/sim/
  final_html`) plus JSON-safe summaries (`plan_summary()`, deduped `runs[]`
  with `updated_str`). Client state `S = {token, plan, cfgid}` in
  `index.html`; tab bodies are injected in place, never navigated.
  `fillOverview(data, silent)` fills all six result tabs at once
  (`resetOverview` clears them).   `config.html` / `sector.html` are gone
  (replaced by `_zones/_valves/_pipes/_other/_simulation/_final_result.html`
  partials).
  **"Use this config" stays in the same page**: it fetches `{op:overview}`
  and fills the Zones (per-sector maps + zone tables + **Confirm Zones**
  button), Valve (principal 90 mm + secondary 32 mm tables), Pipes
  (90/63/32), Other Elements (big map + add form + AI verdicts), Simulation
  (ROI form + AI proposal) and Final Result (full map + legend + report +
  Export PDF) tabs, then switches to Zones. Basin/sector edits silently re-fetch the open overview so
  all tabs stay in sync. Basin Apply updates the map via the iframe `srcdoc`
  attribute (not `innerHTML` — that never re-rendered).
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
    with the **actual sector name** (custom renames included,
    `max-w-20 truncate`; native checkbox square is `display:none`;
    a checked pill glows via `.sector-check:has(.sector-chk:checked)`).
    **Multiple boxes can be checked at once**; all checked sectors are
    highlighted in the map, each checked sector expands a **sector accordion**
    (`.sector-accordion`, 3-column EN / data / AR grid: name, area, centroid,
    entry point, zone angle, zone count; new i18n keys `SECTOR_NAME`,
    `CENTROID`, `ENTRY_POINT`, `ZONE_ANGLE`, `ZONES_COUNT` EN+AR), and clicking
    a sector *in* the map toggles its checkbox **and** its accordion.
    The toolbar (`tool-btn`, rounded, two stacked lines via
    `bv(key)` = Arabic on top + English below) holds Add/Edit/Rename/Merge/Remove
    in a centred `justify-between` row: `MANAGE` EN left, buttons middle, AR
    right — **no `.sector-status` line**. Bilingual JS strings live in a hidden
    global `#sector-i18n` div (`data-tsel/tneed/tmerge/tdraw/tedit/tfin/tcancel/tsaving`
    via `ts()`); `statusNode()` returns that store, `setStatus` only surfaces
    `tneed`/`tmerge` through the top error banner (`terrHtml`), hints are
    signalled by the armed **Done** button state, and checkbox/map-select
    changes clear the banner via `hideError()`. `withSectorMap` guards null
    frames.
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
- **Sector management** (v0.8.0, toolbar centred v0.9.8, status line removed
   v0.9.8): each config card has a **taller map**
   (`iframe.map.tall`, 560 px) and a centred toolbar of `tool-btn` buttons with
    `data-op` = `add | edit | rename | merge | swap | remove` and **no status line**
   (guidance via top error banner + armed Done state; strings from global
   `#sector-i18n`).
   `core/engine.py` exposes `apply_sector_op(plan, cfg, op, idx, idx2, name,
   ring)` → rebuilds the sector chain/entries via `recompute_sectors` (re-sorts
   by distance to basin, keeps custom non-`S\d+` names) and the full
    zones/valves/pipes pipeline. Rules: rename needs a non-empty name unique
    among the other sectors (case-insensitive); any style is accepted, including
    `S<number>` (auto-naming on add skips taken names, so no collision);
    remove needs ≥ 2 sectors; add/edit need a valid ring inside the land (≥ 90 % of
    area, ≥ 60 m²) — add **carves** the new polygon out of every existing sector
    (`difference`); merge unions two sectors keeping the first's name.
    **Rename also rejects duplicate names** (case-insensitive match against the
    other sectors → `"That sector name is already used. Pick a unique name."`).
    All sector-op error strings are bilingual via `i18n.err` (`ERRORS` entries).
    Client `applySectorOp` and the basin submit never fail silently any more:
    missing token, non-200, bad JSON or empty fragment all show the bilingual
    `NETWORK_ERROR` (`#sector-i18n` `data-tnet`) in the top error banner.
   `core/mapper._sector_manage_js(cfg)` adds draw/edit tools (`startDraw`,
   `startEdit(idx, ring)` that rewires vertex drags, `finishDraw/finishEdit`,
   Escape = cancel) posting `sector-draw` / `sector-edit` / `sector-cancel`
    (+ `sector-draw-start` / `sector-edit-start`) to `window.top`.
    Ops: `{op:sector_coords}` (returns the closed ring) and
    `{op:sector_action}` (JSON `{cfgid, action, idx, idx2,
    name, ring}`) → applies the op, regenerates `cfg_maps`, persists via
    `STORE.save`, clears the stale `overview_maps`/`sector_maps` for that cfg,
    returns `{ok, error?, sectors_html, plan}` (the `_sectors_result.html`
    fragment `index.html` swaps into `#sectors-result`; the client re-fetches
    an open overview afterwards). Draw flow in the live map is
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
  Jinja globals in `app.py`: `t`, `bt`, `btcfg`, `bi`, `i18n_css`. Map tooltips use
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
  Zones, Valve, Pipes, Other Elements, Simulation, Final Result** (pipeline stages; placeholders that show
  `t('UPLOAD_FIRST')` = "Upload First a File (csv/kml)" when nothing was
  uploaded yet). Tab buttons use `bi(key)` for bilingual text (EN + AR inline).
  Tab switching is a small vanilla-JS snippet in `index.html`; styles live in
  `base.html` (`.tab-btn`, `.tab-panel`). Default (active) tab: **Upload**
  when no result card exists, **Basin** once a plan was analysed
  (`#upload-result-card` is present).
  The "Analyse the plot" button is wider than its card (`-mx-6` bleed).
- Config headings show bilingual Arabic translations of the base name via
  `btcfg()` → `config_ar()`: "Balanced grid" → "شبكة متوازنة",
  "Mosaic (mixed cell sizes)" → "فسيفساء (خلايا بأحجام مختلفة)",
  "Fine (smaller cells)" → "دقيق (خلايا أصغر)",
  "Existing sectors" → "قطاعات موجودة". The count suffix is localised
  ("(N cells)" → "(N خلايا)", "(N polygons)" → "(N مضلّعات)").
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
  `name, all_boundaries[{name,description,poly,is_land}], boundaries[{name,description,is_land,area_m2}],
  water_points[{lon,lat}], n_water_points, land (Polygon ll), land_area_m2,
  water{lon,lat}, basin{lon,lat,z,has_elev,max_elev,dist_water_m}, basin_m,
  max_elev_m, configs[], existing_sectors(bool),
  other_elements[{id,kind,lon,lat,size,note,necessary,verdict,suggestion}],
  simulation{years,capex,annual_cost,annual_revenue,crop},
  _proj (Projector), _basin_m, _land_m`

  `config`: `id, name, angle, n_sectors, sectors[], ready, zones_confirmed`
  and after `engine.extend(plan, cid)`: `zones[], valves[], pipes`
  (`pipes = {principal:{diameter_mm:90, line, len_m},
              majors:[{zone,sector,diameter_mm:63,line,len_m}],
              minors:[{zone,sector,diameter_mm:32,line,len_m}]}`)

Basin editing: `engine.set_basin(plan, lon, lat)` validates the point is
inside the land (`_land_m.distance(pt) <= 1.0`), updates `basin`,
`_basin_m`/`basin_m`, recomputes `dist_water_m` and re-runs `sectorise` /
`_existing_config` (entries/ordering + zones/pipes then come from the new
point). Op `{op:basin}` (`{token, lon, lat}`) returns JSON `{ok, error_html?,
basin{lon,lat,dist_water_m}, basin_map,
sectors_html}`. `index.html` then swaps the
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

   `valve`: principal `{id:P:<sector>, kind:principal, sector, diameter_mm:90, lon, lat,
   point, name}` + secondary `{id:S:<zone>, kind:secondary, sector, zone, diameter_mm:32,
   lon, lat, point, name}` (added valves get `id:C:<hex>` + `custom:true`;
   moved valves get `moved:true`). Per-config manual state:
   `valve_overrides{(kind,sector,zone):[lon,lat]}`, `removed_valves[[kind,sector,zone]]`,
   `custom_valves[]`, re-applied by `_apply_valve_customization` at the end of
   every rebuild (moved secondary valves pull their 63/32 mm pipes along;
   stale keys pruned; sector rename/swap migrate keys via `_rekey_sector`;
   zone structural edits reset that sector's tweaks). Op `{op:valve_action}`
   (`{cfgid, action: add|move|remove, valve_id, kind, lon, lat, sector, zone}`)
   → `apply_valve_op`, same map-invalidation + overview-fragment pattern as
   `zone_action`. Valve tab (`_valves_result.html`) shows X/Y per row with
   Edit/Remove buttons + a management card (valve select, kind/sector/zone for
   new, X/Y filled by map click via `mapper._valve_pick_js` → `valve-map-click`
   → `#valve-lon/#valve-lat`); moved rows get `●`, added rows `*`. New i18n keys
   `VALVE_MGMT, VALVE_MGMT_SUB, VALVE_TARGET, VALVE_NEW, VALVE_ADD, VALVE_MOVE,
   VALVE_PICK` + errors `"Valve not found."`, `"The valve must lie inside the
   land boundary."` (EN+AR).

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
    Modal is fully bilingual: header shows EN left / AR right via `di` flex,
    body and buttons show AR on top / EN below via `bv` flex; JS parses
    plain `ts()`/`tsf()` data-* text and renders bilingual HTML with
    `modalH()`/`modalV()` helpers.
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
16. v0.9.6: **UI polish** — fixed extra `</div>` in `index.html` that broke
     tab padding; fixed `-mx-6` bleed to `-mx-5` + `overflow-hidden` on config
     cards; added bilingual tab labels (`bi(key)` inline helper) for all 8 tabs; 
     bilingual placeholder headings for future tabs (Zones, Valve, Pipes, Final 
     Result) and "error" label; added `ZONES_TITLE` key for sector.html; 
     bilingual config names via `config_ar()` (Balanced grid → شبكة متوازنة, 
     Mosaic → فسيفساء, Fine → دقيق, Existing sectors → قطاعات موجودة) with 
     localised count suffixes (cells → خلايا, polygons → مضلّعات); fixed 
     `STEP_SECTORS` (up to 5 → 3); inline `.di` / `.legend` CSS fixes to prevent 
     tall stacked legends/info lines; fixed `map_sector` KeyError on 
     non-contiguous zone indices (robust colouring by position); engine zones 
     now numbered contiguously per sector even when a sliver piece is dropped.
17. v0.9.7: **modal bilingual** — sector Rename/Remove modal now fully
    bilingual: header uses `di` flex (EN left, AR right), body message and
    footer buttons use `bv` flex (AR on top row, EN below). JS parses plain
    `ts()`/`tsf()` data attributes and renders via `modalH()`/`modalV()`
    helpers; added `bvfmt()` helper to i18n.py + registered in app.py globals.
18. v0.9.8: **dynamic checkbox labels + toolbar bilingual header** — sector
    checkbox labels now show the **actual sector name** (including custom
    renames) instead of sequential S1/S2/S3; label uses `max-w-20 truncate`
    for long names. Manage toolbar header split into EN label on the left
    (`tl('MANAGE')[0]`) and AR label on the right (`tl('MANAGE')[1]`) with
    the tool buttons between them; AR + status grouped in a right-aligned div.
19. v0.9.8: **centred toolbar, status line removed** — Manage row is now
    `justify-between` (EN label left, buttons centred, AR label right); the
    `.sector-status` span and its `data-t*` strings are gone.
20. v0.9.8: **sector accordion** — each checked sector expands a 3-column
    EN / data / AR card (name, area, centroid, entry, zone angle, zone count);
    new i18n keys `SECTOR_NAME, CENTROID, ENTRY_POINT, ZONE_ANGLE,
    ZONES_COUNT` (EN+AR) + `.sector-accordion` neon style in `base.html`;
    checkbox `change` toggles the accordion.
21. v0.9.9: **toolbar JS repair after status-span removal** — bilingual
    strings moved to a hidden global `#sector-i18n` div; `statusNode()` reads
    the store, `setStatus` only surfaces `tneed`/`tmerge` via the top error
    banner (`terrHtml`), select changes clear the banner, map-driven
    `sector-select` also toggles the accordion, `withSectorMap` guards null
    frames; `VERSION` → 0.9.9 with README/PROMPT resynced.
22. v0.10.0: **unique sector names + loud failures** — rename rejects an
    already-used name (case-insensitive, other sectors only) with a bilingual
    error; all sector-op messages added to `ERRORS` (EN+AR); new `NETWORK_ERROR`
    key (`#sector-i18n` `data-tnet`); `applySectorOp` and basin submit surface
    missing-token / non-200 / bad-JSON / empty-fragment failures in the top
    error banner instead of silently doing nothing.
23. v0.10.1: **Load list shows land name + last-save date** — each row shows
    the plan name, `SAVED_AT` + `fmt_dt(run.updated_at)` (`YYYY-MM-DD HH:MM`,
    new Jinja global in `app.py`; new i18n key `SAVED_AT` EN+AR), token kept
    small; `FileStore.list_runs` now sorts newest-first like Mongo.
24. v0.10.2: **rename accepts any unique name** — the `S<number>` restriction
    is dropped (uniqueness check + collision-skipping auto-naming make it
    unnecessary); only empty and duplicate names are rejected.
25. v0.11.0: **single-URL SPA** — the browser only uses `/` (`GET` shell,
    `POST` multipart upload or JSON `{op}`: `load/list_runs/basin/
    sector_coords/sector_action/overview`); `config.html`/`sector.html` deleted,
    replaced by `_zones/_valves/_pipes/_final_result.html` partials;
    **Use this config fills Zones/Valve/Pipes/Final tabs in the same page**;
    basin Apply fixed to swap the map via `srcdoc`; open overviews re-fetch
    after edits; Load rows carry pre-formatted `updated_str`.
26. v0.11.1: **sector pills sorted A-Z** — `_sectors_result.html` loops
    `cfg.sectors|natsort` (new Jinja filter in `app.py`: case-insensitive
    natural sort) for pills and accordions, so renames re-order the list
    (maps + Zones tab keep basin-distance/idx order).
31. v0.13.2: **KML `description` is the element type** — shared word-based
    matchers (`_is_water_type`: water/point/source/puit/valve/w,
    `_is_land_type`: boundary/parcel/terrain… EN+FR+AR) in `core/parser.py`;
    water-described polygons yield their centre as a water point, land-described
    points are skipped as labels; description-less placemarks keep the old rule;
    CSV `type` matching unified on the same helper.
29. v0.13.0: **upload summary card in Upload tab** — new `_upload_card.html`
    partial (name, area, water, basin, per-config sector counts, `data-go-tab`
    button to Basin); returned as `upload_html` in the full payload, injected
    into `#upload-file-card`; upload stays on the Upload tab, load still jumps
    to Basin; `plan_summary` gains `n_boundaries`.
30. v0.13.1: **file-contents enumeration** — `analyse` adds `boundaries`
    (+ per-polygon m² areas), `water_points` and `n_water_points` to the plan
    (also mirrored in `plan_summary`); the upload card lists each element type
    (land boundary, extra polygons, water points) with counts; new i18n keys
    `FILE_CONTENTS, EXTRA_POLYGONS, WATER_POINTS` (EN+AR); old saved plans
    without the keys still render (`or []` guards).
32. v0.14.0: **extra polygons split by `description`** — parser keeps
    `description` per polygon through `all_boundaries`/`boundaries`;
    `_existing_config` groups kept polygons by description (A-Z, undescribed
    last; basin-distance within groups) with per-group names `<desc> <k>`
    (capped 32 chars, deduped; undescribed keep `S{rank}`);     upload card groups
    extras via `groupby('description')`.
33. v0.15.0: **Swap button (after Merge)** — `swap` op exchanges the names of
    two checked sectors and rebuilds zones/valves/pipes; new i18n keys
    `SECTOR_SWAP, SWAP_NEED` (EN+AR) + bilingual swap error; toolbar order is
    Add/Edit/Rename/Merge/**Swap**/Remove.
34. v0.16.0: **step maps** — Use this config draws no valves/pipes: Zones cards
    use `map_sector(..., valves=False, pipes=False)`; new `map_config_valves`
    (sectors+valves) and `map_config_pipes` (sectors+piping) maps render in the
    Valve/Pipes tabs; full map stays in Final; `maps_v=2` invalidates old cached
    sector artwork; `load` no longer re-saves (preserves cached maps).
28. v0.12.1: **Load rows are 3 columns** — name+token | centred last-save
    datetime | Load button (`sm:grid-cols-3`, stacked on mobile), in both the
    server rows and the JS `refreshRuns` builder.
27. v0.12.0: **sector detail modal** — every Zones card has an Open button
    (`.sector-open-btn` with `data-cfg/idx/name`) launching `#sector-detail-modal`
    (large map copied from the card `srcdoc`, zone table cloned, new i18n key
    `CLOSE` EN+AR); Add/Edit/Rename/Remove act on that sector (rename/remove via
    the existing confirm modal; edit/add close the modal, jump to Sectors and arm
    the tool programmatically); Escape/backdrop/Close dismiss.
35. v0.17.0: **land-keyed storage, zone management, new tabs** —
    land name is the unique key (`_token_for_land` reuses the token on
    re-upload; `_dedup_runs` shows one row per land; `{op:delete_run}` +
    Delete button per Load row; every step re-saves via `_persist`;
    `maps_v=3`, new `other_maps` store); valves are now **principal 90 mm
    per sector + secondary 32 mm per zone**, pipes **90/63/32 mm**
    (`_rebuild_valves_pipes` keeps valves/pipes in sync after zone edits);
    **zone management** (`{op:zone_action}` → `apply_zone_op`: rename /
    remove / split-by-line via X/Y start+stop / confirm; `zones_confirmed`
    flag; **Confirm Zones** button ends the Zones tab and jumps to Valve);
    sector modal gained a **zone-mgmt box** (zone select, X1/Y1/X2/Y2,
    Trace-on-map via `setZonePick` + `zone-pick` messages, Split/Rename/
    Remove); new **Other Elements** tab (`map_other_elements` big map,
    click-to-fill `other-map-click`, `{op:other_add/other_remove}`,
    heuristic `analyse_other_element` verdict + cheaper/smoother
    suggestion); new **Simulation** tab before Final (`compute_simulation`
    ROI table + break-even, `{op:sim_save}`, AI proposal `ai_proposal`);
    **Final Result** now draws zones + both valve kinds + other elements
    and adds a detailed land **report + Export PDF** (`window.print` +
    print CSS); new partials `_other_result` / `_simulation_result`;
    tab bar is Load/Upload/Basin/Sectors/Zones/Valve/Pipes/Other
    Elements/Simulation/Final Result.
36. v0.18.0: **valve management** — every valve is Add/Edit/Remove-able from
    the Valve tab (see data-model note above for the override-layer design).
37. v0.19.0: **zone labels** — `mapper.map_sector` (Zones-tab maps) draws a
    permanent `DivIcon` badge with the zone name on each zone centroid
    (`_zone_label`, HTML-escaped), so names are visible without hovering.