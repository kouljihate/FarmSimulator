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
  The result page then shows the "EXISTING_TITLE/SUB" heading.
- **Maps are OSM-only** (requirement 1): `core/mapper.py` `_render_base` uses
  `tiles="OpenStreetMap"`, no satellite tiles, no `LayerControl`. There must be
  zero `ArcGIS` / satellite / layer-control strings in map output.
- Persistence: `/upload` saves `uploads/<token>.pkl` (pickle of the plan);
  `get_plan()` reloads from disk on cache miss so tokens survive restarts.
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
- Home page has a **centred pill tab bar**: **Part 1** (upload flow) + **Tab
  2..Tab 6** placeholders. Tab switching is a small vanilla-JS snippet in
  `index.html`; styles live in `base.html` (`.tab-btn`, `.tab-panel`).
  The "Analyse the plot" button is wider than its card (`-mx-6` bleed).
- "Accepted formats" and "What Part 1 produces" cards render the body as **two
  columns: English left, Arabic right** (via `tl(key)` = `(en, ar)` plain-text
  pairs; Arabic column is `dir=rtl` with the VIP RAWY family).
- Home header shows only the bilingual app name: **Farm Simulator** (left) +
  **محاكي المزرعة** (right). Browser tab title carries the Part 1 title
  (`Farm Simulator - Part 1 - irrigation network`).
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
max_elev_m, configs[], existing_sectors(bool), _proj (Projector), _basin_m`

`config`: `id, name, angle, n_sectors, sectors[], ready` and after
`engine.extend(plan, cid)`: `zones[], valves[], pipes`
(`pipes = {principal:{diameter_mm:90, line, len_m},
            majors:[{zone,diameter_mm:50,line,len_m}],
            minors:[{zone,diameter_mm:32,line,len_m}]}`)

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
  update `requirements.txt` (currently flask, shapely, pyproj, folium) and note
  it.
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