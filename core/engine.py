"""The planning engine.

Pipeline (this first part):
  1. basin   -> best spot near the water point, at a favourable elevation
  2. sectorisation -> up to 5 config maps of the land split into sectors <= 10000 m2
  3. zonage  -> every sector split into 3 equal-area zones (Z1, Z2, Z3)
  4. valves  -> principal 90 mm valve per sector + secondary 32 mm valve per zone
  5. piping  -> 90 mm principal, 63 mm majors, 32 mm minors
"""
import math as _math
import re as _re
import uuid as _uuid

from shapely.affinity import affine_transform as _affine
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, split as _shapely_split, unary_union
from shapely.validation import make_valid

from .geo import Projector, _affine_params, main_axis_angle, sweep_split
from .sector import partition

MAX_SECTOR_AREA = 10000.0
N_ZONES = 3
MIN_EXISTING_COVERAGE = 0.5  # sectors already in the file must cover >= 50% of the land
ROW_SPACING_DEFAULT = 5.0
ROW_SPACING_MIN = 1.0
ROW_SPACING_MAX = 20.0

OTHER_KINDS = (
    "pressure_reducer",
    "connector_90_63",
    "connector_63_32",
    "tee_63",
    "elbow_63",
    "elbow_32",
    "filter_90",
    "pump_booster",
)

TREE_DIST_DEFAULT = 5.0
TREE_DIST_MIN = 0.5
TREE_DIST_MAX = 100.0

TREE_TYPES = (
    "none",
    "olive",
    "citrus",
    "almond",
    "pomegranate",
    "apple",
    "date_palm",
    "grape",
    "fig",
)


# --------------------------------------------------------------------------- #
# Land / terrain helpers
# --------------------------------------------------------------------------- #
def _z_key(lon, lat):
    return (round(lon, 7), round(lat, 7))


def _polygon_area_m2(poly, proj):
    return proj.to_m(poly).area


def _prefer_polygon(polygons, water_point):
    """Pick the parcel that holds the water point, else the biggest one."""
    if not polygons:
        return None
    if water_point is not None:
        wp = Point(water_point)
        for p in polygons:
            if p["polygon"].contains(wp):
                return p
    return max(polygons, key=lambda p: p["polygon"].area)


def _as_multi(poly):
    if poly.geom_type == "MultiPolygon":
        return poly
    return MultiPolygon([poly])


# --------------------------------------------------------------------------- #
# Basin
# --------------------------------------------------------------------------- #
def choose_basin(land, project):
    """land: {'polygon_m': Polygon-like, 'vertices_z': [(lon,lat,z)]}.

    Returns dict with lonlat point, elevation info and the reasoning used.
    """
    poly_m = land["polygon_m"]
    water = land["water_m"]

    # elevation lookup keyed on lon/lat
    elev = {}
    for lon, lat, z in land.get("vertices_z", []) or []:
        if z is not None and z != 0:
            elev[_z_key(lon, lat)] = z
    has_elev = bool(elev)

    # base: nearest boundary point to the water point (the water enters there)
    base_pt = nearest_points(poly_m.boundary, Point(water))[0]

    candidates = []
    seen = set()
    for x, y in poly_m.exterior.coords:
        seen.add((round(x, 2), round(y, 2)))
        candidates.append(Point(x, y))
    candidates.append(base_pt)

    # candidate lon/lat to look up elevation
    def _lonlat_lookup(pt, elev):
        """Find nearest lon/lat vertex elevation for a UTM point."""
        best = None
        best_z = None
        for kl, kz in elev.items():
            d = Point(kl).distance(Point(project.to_lonlat(pt).x, project.to_lonlat(pt).y))
            # compare in metres: project the key point back to UTM
            kl_pt = project.to_m(Point(kl))
            dd = kl_pt.distance(pt)
            if best is None or dd < best:
                best = dd
                best_z = kz
        return best_z

    if has_elev:
        # max elevation vertex of the whole land
        maxz = max(elev.values())
        best_vertex = [k for k, v in elev.items() if v == maxz][0]
        max_elev = {"lon": best_vertex[0], "lat": best_vertex[1], "z": maxz}
    else:
        max_elev = None

    scored = []
    for cand in candidates:
        if not poly_m.contains(cand) and not poly_m.boundary.distance(cand) < 1.0:
            continue
        dist = cand.distance(Point(water))
        z = _lonlat_lookup(cand, elev) if has_elev else 0.0
        scored.append((cand, dist, z))

    if not scored:
        scored = [(base_pt, base_pt.distance(Point(water)), 0.0)]

    dmax = max((s[1] for s in scored), default=1.0) or 1.0
    zmax = max((s[2] for s in scored), default=1.0)
    zmin = min((s[2] for s in scored), default=0.0)
    zrange = (zmax - zmin) or 1.0

    def score(item):
        cand, dist, z = item
        d_norm = min(dist / dmax, 1.0)
        z_norm = (z - zmin) / zrange if has_elev else 0.0
        return 0.6 * z_norm - 0.4 * d_norm

    best, best_d, best_z = max(scored, key=score)
    pt_lonlat = project.to_lonlat(best)
    return {
        "lon": pt_lonlat.x,
        "lat": pt_lonlat.y,
        "z": best_z if has_elev else None,
        "has_elev": has_elev,
        "max_elev": max_elev,
        "dist_water_m": best_d,
    }


# --------------------------------------------------------------------------- #
# Sectorisation
# --------------------------------------------------------------------------- #
def _sector_defs(land_m):
    """Deterministic list of (name, axis_angle, target_frac, fraction, pick).

    Varying the target cell size and the split-area fraction produces several
    visibly different alternatives from the same land (uniform vs mixed cell
    sizes, coarse vs fine granularity). All share the field-axis-aligned frame
    because a global diagonal orientation degenerates into thin slivers on
    elongated parcels.
    """
    axis = main_axis_angle(land_m)
    return [
        ("Balanced grid", axis, 1.00, 0.50, "largest"),
        ("Mosaic (mixed cell sizes)", axis, 1.00, 0.68, "largest"),
        ("Fine (smaller cells)", axis, 0.55, 0.50, "largest"),
    ]


def sectorise(land_m, proj, basin_pt_m):
    """Return a list of config dicts, each with ordered sectors + entries.

    Sectors are produced by a recursive area-balanced split (see core.sector),
    ordered so S1 is the sector closest to the basin point, then S2, ... The
    per-sector *entry* is the boundary point nearest the previous sector's
    entry (the chain starts at the basin point).
    """
    configs = []
    seen = set()
    for cid, (base_name, axis, target_frac, fraction, pick) in enumerate(_sector_defs(land_m)):
        cells = partition(land_m, MAX_SECTOR_AREA * target_frac, axis, fraction, pick)
        if not cells:
            continue

        # drop configs whose partition is identical to one already produced
        sig = tuple(sorted(
            (round(c.centroid.x, 1), round(c.centroid.y, 1), round(c.area, 1))
            for c, _ in cells
        ))
        if sig in seen:
            continue
        seen.add(sig)

        order = sorted(
            range(len(cells)),
            key=lambda i: cells[i][0].centroid.distance(basin_pt_m),
        )

        sectors = []
        cur = basin_pt_m
        for rank, i in enumerate(order, start=1):
            piece_m, zone_angle = cells[i]
            poly_ll = proj.to_lonlat(piece_m)
            entry = nearest_points(piece_m.boundary, Point(cur))[0]
            sectors.append({
                "idx": rank,
                "name": "S{0:d}".format(rank),
                "poly_m": piece_m,
                "poly": poly_ll,
                "centroid": proj.to_lonlat(piece_m.centroid),
                "area_m2": piece_m.area,
                "entry": proj.to_lonlat(entry),
                "entry_m": entry,
                "zone_angle": zone_angle,
            })
            cur = entry

        configs.append({
            "id": cid,
            "name": "{0} ({1:d} cells)".format(base_name, len(sectors)),
            "angle": axis,
            "n_sectors": len(sectors),
            "sectors": sectors,
            "ready": False,
        })
    return configs


# --------------------------------------------------------------------------- #
# Zones / valves / piping for a chosen config
# --------------------------------------------------------------------------- #
def _zone_order(sector, pieces, basin_m, scan_angle):
    """Order zone pieces so Z1 is the one nearest the basin side.

    `scan_angle` is the angle of the zone cut lines (the same angle handed to
    `sweep_split`); the zone pieces are stacked along `scan_angle + 90`.
    """
    from shapely.affinity import affine_transform

    from .geo import _affine_params

    stack = scan_angle + 90.0  # direction the zone pieces are stacked along
    origin = sector["poly_m"].centroid
    fwd, _ = _affine_params(stack, origin)
    centers = []
    for p in pieces:
        fp = affine_transform(p, fwd)
        centers.append(fp.centroid.x)
    # basin location along this frame
    bframe = affine_transform(Point(basin_m), fwd).x if basin_m is not None else centers[0]
    order = sorted(range(len(pieces)), key=lambda i: (abs(centers[i] - bframe), centers[i]))
    # within that, keep the monotonic global order for readability
    return order


def _principal_chain(plan, cfg, order=None):
    """Principal 90 mm line: basin, then sector entries in visit order."""
    proj = plan["_proj"]
    if order:
        byname = {s.get("name"): s for s in cfg.get("sectors", [])}
        secs = [byname[n] for n in order if n in byname]
        secs += [s for s in cfg.get("sectors", []) if s.get("name") not in (order or [])]
    else:
        secs = cfg.get("sectors", [])
    pts = [plan["_basin_m"]] + [s["entry_m"] for s in secs]
    principal_m = LineString(pts)
    return principal_m, proj.to_lonlat(principal_m)


def _nearest_on(line_m, pt_m):
    return nearest_points(line_m, Point(pt_m))[0]


def extend_config(plan, project, cfg, basin_m, max_elev_m):
    """Add zones, valves and pipes to a chosen sectorisation config.

    Valves: one principal 90 mm valve per sector (at the sector entry) plus
    one secondary 32 mm valve per zone. Pipes: 90 mm principal
    (basin -> sector entries), 63 mm majors (sector valve -> zone valves),
    32 mm minors (zone valve -> zone supply point).
    """
    if cfg.get("ready"):
        return cfg

    principal_m, principal_ll = _principal_chain(plan, cfg)

    zones_all = []
    valves = []
    majors = []
    minors = []

    for sector in cfg["sectors"]:
        sector_m = sector["poly_m"]
        scan_angle = sector.get("zone_angle", cfg["angle"] + 90.0)
        pieces = sweep_split(sector_m, scan_angle, N_ZONES)
        order = _zone_order(sector, pieces, basin_m, scan_angle)

        sector["zones"] = []
        entry_m = sector["entry_m"]
        entry_ll = project.to_lonlat(entry_m)
        valves.append({
            "id": _valve_id("principal", sector["name"], sector["name"]),
            "kind": "principal",
            "sector": sector["name"],
            "zone": sector["name"],
            "diameter_mm": 90,
            "lon": entry_ll.x,
            "lat": entry_ll.y,
            "point": entry_ll,
            "name": "Valve principal {0}".format(sector["name"]),
        })

        zidx = 0
        for pi in order:
            zone_m = pieces[pi]
            if zone_m is None or not zone_m.geom_type.startswith("Polygon"):
                continue
            if zone_m.area <= 1e-6:
                continue
            zidx += 1
            zone_ll = project.to_lonlat(zone_m)
            # secondary valve on the zone boundary closest to the sector entry
            valve_m = nearest_points(zone_m.boundary, Point(entry_m))[0]
            valve_ll = project.to_lonlat(valve_m)

            # major pipe 63 mm: nearest principal tap -> zone secondary valve
            tap_m = _nearest_on(principal_m, valve_m)
            major_m = LineString([tap_m, Point(valve_m)])
            major_ll = project.to_lonlat(major_m)

            # minor pipe 32 mm: nearest major point -> zone water supply
            target_m = zone_m.centroid
            tap2_m = _nearest_on(major_m, target_m)
            minor_m = LineString([tap2_m, target_m])
            minor_ll = project.to_lonlat(minor_m)

            zone = {
                "idx": zidx,
                "name": "S{0}Z{1:d}".format(sector["idx"], zidx),
                "poly_m": zone_m,
                "poly": zone_ll,
                "area_m2": zone_m.area,
                "centroid": project.to_lonlat(target_m),
                "tree": "none",
                "tree_dist": TREE_DIST_DEFAULT,
                "tree_pct": 100.0,
            }
            zones_all.append(zone)

            valve = {
                "id": _valve_id("secondary", sector["name"], zone["name"]),
                "kind": "secondary",
                "sector": sector["name"],
                "zone": zone["name"],
                "diameter_mm": 32,
                "lon": valve_ll.x,
                "lat": valve_ll.y,
                "point": valve_ll,
                "name": "Valve secondary {0}".format(zone["name"]),
            }
            valves.append(valve)

            majors.append({
                "pid": "M:{0}".format(zone["name"]),
                "zone": zone["name"],
                "sector": sector["name"],
                "diameter_mm": 63,
                "line": major_ll,
                "len_m": major_m.length,
            })
            minors.append({
                "pid": "m:{0}".format(zone["name"]),
                "zone": zone["name"],
                "sector": sector["name"],
                "diameter_mm": 32,
                "line": minor_ll,
                "len_m": minor_m.length,
            })
            sector["zones"].append(zone)

    cfg["ready"] = True
    cfg["zones"] = zones_all
    cfg["valves"] = valves
    cfg["pipes"] = {
        "principal": {"pid": "P", "diameter_mm": 90, "line": principal_ll, "len_m": principal_m.length},
        "majors": majors,
        "minors": minors,
    }
    _apply_valve_customization(plan, cfg)
    _number_valves(cfg)
    _apply_pipe_customization(plan, cfg)
    return cfg


# --------------------------------------------------------------------------- #
# Whole-plot analysis
# --------------------------------------------------------------------------- #
def _nat_key(text):
    return [int(t) if t.isdigit() else t.lower()
            for t in _re.split(r"(\d+)", text or "")]


def _existing_config(extra, land_m, proj, basin_m):
    """Build a single config from sector polygons already present in the file.

    Returns None when the extra polygons do not plausibly form a sector layout
    (too small, unrelated to the land, or covering under 50% of it) - in that
    case the planner should generate fresh suggestions instead.
    """
    kept = []
    for p in extra:
        gm = proj.to_m(p["polygon"])
        if gm.is_empty:
            continue
        if not gm.is_valid:
            gm = make_valid(gm)
        if gm.is_empty or gm.area < 100.0:
            continue
        inter = gm.intersection(land_m)
        if inter.area < 0.5 * gm.area:
            continue
        kept.append((gm, (p.get("description") or "").strip()))
    if not kept:
        return None
    total = unary_union([gm for gm, _ in kept])
    if total.is_empty or total.intersection(land_m).area < MIN_EXISTING_COVERAGE * land_m.area:
        return None

    groups = {}
    for i, (gm, desc) in enumerate(kept):
        groups.setdefault(desc.lower(), {"display": desc, "members": []})["members"].append(i)
    ordered = sorted(groups.values(),
                     key=lambda g: (not g["display"], _nat_key(g["display"])))
    for g in ordered:
        g["members"].sort(key=lambda i: kept[i][0].centroid.distance(basin_m))
    sectors = []
    used = set()
    cur = basin_m
    rank = 0
    for g in ordered:
        for k, i in enumerate(g["members"], start=1):
            rank += 1
            piece_m = kept[i][0]
            if g["display"]:
                base = (g["display"][:32].rstrip() or g["display"])
                name, n = "{0} {1:d}".format(base, k), k
                while name.lower() in used:
                    n += 1
                    name = "{0} {1:d}".format(base, n)
            else:
                name = "S{0:d}".format(rank)
                while name.lower() in used:
                    rank += 1
                    name = "S{0:d}".format(rank)
            used.add(name.lower())
            poly_ll = proj.to_lonlat(piece_m)
            entry = nearest_points(piece_m.boundary, Point(cur))[0]
            sectors.append({
                "idx": rank,
                "name": name,
                "poly_m": piece_m,
                "poly": poly_ll,
                "centroid": proj.to_lonlat(piece_m.centroid),
                "area_m2": piece_m.area,
                "entry": proj.to_lonlat(entry),
                "entry_m": entry,
                "zone_angle": main_axis_angle(piece_m) + 90.0,
            })
            cur = entry

    return {
        "id": 0,
        "name": "Existing sectors ({0:d} polygons)".format(len(sectors)),
        "angle": 0.0,
        "n_sectors": len(sectors),
        "sectors": sectors,
        "ready": False,
    }


def analyse(parsed, max_sector_area=MAX_SECTOR_AREA):
    """Full pipeline entry point used by the web app."""
    if not parsed or not parsed.get("polygons"):
        raise ValueError("No boundary polygon found in the upload.")
    polygons = list(parsed["polygons"])
    land_pkg = _prefer_polygon(polygons, parsed.get("water_points") and parsed["water_points"][0])

    pick = parsed["water_points"][0] if parsed.get("water_points") else None
    if pick is None:
        # fall back to the presumed natural outflow: centroid of the land
        pick = land_pkg["polygon"].representative_point()
        pick = (pick.x, pick.y)
    proj = Projector(*pick)

    land_m = proj.to_m(land_pkg["polygon"])
    if land_m.is_empty or land_m.area <= 0:
        raise ValueError("Boundary polygon is empty after projection.")

    water_m = proj.to_m(Point(pick))
    land = {
        "polygon_m": land_m,
        "poly": land_pkg["polygon"],
        "vertices_z": land_pkg.get("vertices_z", []),
        "water_m": water_m,
    }

    basin = choose_basin(land, proj)
    basin_m = proj.to_m(Point(basin["lon"], basin["lat"]))

    max_elev_m = None
    if basin.get("max_elev"):
        me = basin["max_elev"]
        max_elev_m = proj.to_m(Point(me["lon"], me["lat"]))

    existing_cfg = None
    extra = [p for p in polygons if p is not land_pkg]
    if extra:
        existing_cfg = _existing_config(extra, land_m, proj, basin_m)

    configs = [existing_cfg] if existing_cfg else sectorise(land_m, proj, basin_m)
    existing_sectors = existing_cfg is not None

    area_m2 = land_m.area

    bounds = []
    for p in polygons:
        is_land = p is land_pkg
        try:
            a = area_m2 if is_land else proj.to_m(p["polygon"]).area
        except Exception:  # noqa: BLE001 - display-only area
            a = 0.0
        bounds.append({"name": p["name"], "description": p.get("description") or "",
                       "is_land": is_land, "area_m2": a})
    water_pts = [
        {"lon": float(w[0]), "lat": float(w[1])}
        for w in (parsed.get("water_points") or [])
    ]

    # small optimisation: compute zones/pipes eagerly for one config? we keep lazy
    for c in configs:
        c.setdefault("zones_confirmed", False)
        c.setdefault("rows_confirmed", False)
        c.setdefault("valves_confirmed", False)
    return {
        "name": parsed.get("name") or "Untitled plot",
        "all_boundaries": [{
            "name": p["name"],
            "description": p.get("description") or "",
            "poly": p["polygon"],
            "is_land": p is land_pkg,
        } for p in polygons],
        "boundaries": bounds,
        "water_points": water_pts,
        "n_water_points": len(water_pts),
        "land": land_pkg["polygon"],
        "land_area_m2": area_m2,
        "vertices_z": land_pkg.get("vertices_z", []),
        "water": {"lon": pick[0], "lat": pick[1]},
        "basin": basin,
        "basin_m": basin_m,
        "max_elev_m": max_elev_m,
        "configs": configs,
        "existing_sectors": existing_sectors,
        "other_elements": [],
        "simulation": {},
        "_proj": proj,
        "_basin_m": basin_m,
        "_land_m": land_m,
    }


def set_basin(plan, lon, lat):
    """Move the basin to a user-provided lon/lat and re-derive everything that
    depends on it (sector ordering/entries, zones, valves and piping).

    Returns (ok, error) where error is None on success.
    """
    proj = plan["_proj"]
    pt = proj.to_m(Point(lon, lat))
    land_m = plan["_land_m"]
    if land_m.is_empty or land_m.distance(pt) > 1.0:
        return False, "Point is outside the land boundary."

    water_ll = plan["water"]
    water_m = proj.to_m(Point(water_ll["lon"], water_ll["lat"]))
    basin = plan["basin"]
    basin["lon"] = float(lon)
    basin["lat"] = float(lat)
    basin["dist_water_m"] = pt.distance(water_m)
    plan["_basin_m"] = pt
    plan["basin_m"] = pt

    if plan.get("existing_sectors"):
        extra = [{
            "name": b["name"],
            "description": b.get("description") or "",
            "polygon": b["poly"],
        } for b in plan["all_boundaries"] if not b["is_land"]]
        cfg = _existing_config(extra, land_m, proj, pt)
        plan["configs"] = [cfg] if cfg else []
    else:
        plan["configs"] = sectorise(land_m, proj, pt)
    for c in plan["configs"]:
        c.setdefault("zones_confirmed", False)
        c.setdefault("rows_confirmed", False)
        c.setdefault("valves_confirmed", False)
    return True, None


def extend(plan, cfgid):
    proj = plan["_proj"]
    cfg = [c for c in plan["configs"] if c["id"] == cfgid]
    if not cfg:
        raise ValueError("Unknown config")
    cfg = cfg[0]
    if cfg.get("ready"):
        _number_valves(cfg)
        _ensure_pipe_pids(cfg)
        return cfg
    return extend_config(plan, proj, cfg, plan["_basin_m"], plan.get("max_elev_m"))


# --------------------------------------------------------------------------- #
# Manual sector management (add / edit / remove / merge / rename)
# --------------------------------------------------------------------------- #
def _sector_num(name):
    """Trailing numeric part of a sector name, for picking the next free one."""
    m = _re.search(r"(\d+)\s*$", name or "")
    return int(m.group(1)) if m else 0


def _find_sector(cfg, idx):
    for s in cfg.get("sectors", []):
        if s["idx"] == idx:
            return s
    return None


def _poly_from_ring(ring):
    """Build a valid (Multi)Polygon (lon/lat) from a closed vertex ring."""
    try:
        pts = [(float(x), float(y)) for x, y in ring]
    except (TypeError, ValueError):
        return None
    if len(pts) < 4:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    poly = Polygon(pts)
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    return poly if not poly.is_empty else None


def recompute_sectors(plan, cfg, polys):
    """Given (poly_m, custom_name) pairs, re-sort by distance to the basin,
    rebuild the sector dicts (entry chain, zone angle) and recompute the whole
    pipeline (zones, valves, pipes) for the config."""
    proj = plan["_proj"]
    order = sorted(
        range(len(polys)),
        key=lambda i: polys[i][0].centroid.distance(plan["_basin_m"]),
    )
    sectors = []
    cur = plan["_basin_m"]
    for rank, i in enumerate(order, start=1):
        piece_m = polys[i][0]
        name = polys[i][1] or ""
        if piece_m.is_empty or piece_m.area <= 1e-6:
            continue
        if not piece_m.is_valid:
            piece_m = make_valid(piece_m)
        if piece_m.is_empty or piece_m.area <= 1e-6:
            continue
        poly_ll = proj.to_lonlat(piece_m)
        entry = nearest_points(piece_m.boundary, Point(cur))[0]
        sectors.append({
            "idx": rank,
            "name": name or "S{0:d}".format(rank),
            "poly_m": piece_m,
            "poly": poly_ll,
            "centroid": proj.to_lonlat(piece_m.centroid),
            "area_m2": piece_m.area,
            "entry": proj.to_lonlat(entry),
            "entry_m": entry,
            "zone_angle": main_axis_angle(piece_m) + 90.0,
        })
        cur = entry

    cfg["sectors"] = sectors
    cfg["n_sectors"] = len(sectors)
    cfg["ready"] = False
    cfg["zones_confirmed"] = False
    cfg["rows_confirmed"] = False
    cfg["valves_confirmed"] = False
    for k in ("zones", "valves", "pipes", "principal_order", "pipe_report"):
        cfg.pop(k, None)
    extend_config(plan, proj, cfg, plan["_basin_m"], plan.get("max_elev_m"))
    return cfg


def _current_polys(cfg):
    return [(s["poly_m"], s.get("name")) for s in cfg["sectors"]]


def apply_sector_op(plan, cfg, op, idx=None, idx2=None, name=None, ring=None):
    """Apply one sector edit to a config in place. Returns (ok, message).

    Supported ops: rename, remove, merge (idx+idx2), swap (idx+idx2),
    add (ring), edit (idx+ring).
    After every operation the config's entries/zones/valves/pipes are rebuilt.
    """
    if op == "rename":
        target = _find_sector(cfg, idx)
        if target is None:
            return False, "Sector not found."
        nm = (name or "").strip()
        if not nm:
            return False, "Empty sector name."
        taken = {s.get("name", "").strip().lower()
                 for s in cfg["sectors"] if s["idx"] != idx}
        if nm.lower() in taken:
            return False, "That sector name is already used. Pick a unique name."
        old_nm = target["name"]
        target["name"] = nm
        _rekey_sector(cfg, old_nm, nm)
        _rekey_pipe_sector(cfg, old_nm, nm)
        recompute_sectors(plan, cfg, _current_polys(cfg))
        return True, None

    if op == "remove":
        if len(cfg["sectors"]) <= 1:
            return False, "Cannot remove the last sector."
        if _find_sector(cfg, idx) is None:
            return False, "Sector not found."
        recompute_sectors(plan, cfg, [
            (s["poly_m"], s.get("name"))
            for s in cfg["sectors"] if s["idx"] != idx
        ])
        return True, None

    if op == "merge":
        a = _find_sector(cfg, idx)
        b = _find_sector(cfg, idx2)
        if a is None or b is None:
            return False, "Select two sectors to merge."
        merged = a["poly_m"].union(b["poly_m"])
        if merged.is_empty:
            return False, "Merge produced an empty sector."
        if not merged.is_valid:
            merged = make_valid(merged)
        if merged.is_empty:
            return False, "Merge produced an empty sector."
        polys = [
            (s["poly_m"], s.get("name"))
            for s in cfg["sectors"] if s["idx"] not in (idx, idx2)
        ]
        polys.append((merged, a.get("name")))
        recompute_sectors(plan, cfg, polys)
        return True, None

    if op == "swap":
        a = _find_sector(cfg, idx)
        b = _find_sector(cfg, idx2)
        if a is None or b is None or idx == idx2:
            return False, "Select two sectors to swap."
        nm_a, nm_b = a.get("name"), b.get("name")
        a["name"], b["name"] = nm_b, nm_a
        _rekey_sector(cfg, nm_a, "__swap_tmp__")
        _rekey_sector(cfg, nm_b, nm_a)
        _rekey_sector(cfg, "__swap_tmp__", nm_b)
        _rekey_pipe_sector(cfg, nm_a, "__swap_tmp__")
        _rekey_pipe_sector(cfg, nm_b, nm_a)
        _rekey_pipe_sector(cfg, "__swap_tmp__", nm_b)
        recompute_sectors(plan, cfg, _current_polys(cfg))
        return True, None

    if op in ("add", "edit"):
        poly = _poly_from_ring(ring)
        if poly is None:
            return False, "Invalid polygon."
        proj = plan["_proj"]
        poly_m = proj.to_m(poly)
        if not poly_m.is_valid:
            poly_m = make_valid(poly_m)
        if poly_m.is_empty or poly_m.area < 60.0:
            return False, "Sector is too small (minimum ~60 m2)."
        inside = poly_m.intersection(plan["_land_m"])
        if inside.area < 0.9 * poly_m.area:
            return False, "The sector must lie inside the land boundary."
        piece_m = inside

    if op == "add":
        names = {s["name"] for s in cfg["sectors"]}
        nxt = max([_sector_num(nm) for nm in names] + [0]) + 1
        while "S{0}".format(nxt) in names:
            nxt += 1
        new_name = "S{0}".format(nxt)
        polys = []
        for s in cfg["sectors"]:
            rest = s["poly_m"].difference(piece_m)
            if rest.is_empty:
                continue
            if not rest.is_valid:
                rest = make_valid(rest)
            if rest.area > 1e-4:
                polys.append((rest, s.get("name")))
        polys.append((piece_m, new_name))
        recompute_sectors(plan, cfg, polys)
        return True, None

    if op == "edit":
        target = _find_sector(cfg, idx)
        if target is None:
            return False, "Sector not found."
        polys = [
            (piece_m if s["idx"] == idx else s["poly_m"], s.get("name"))
            for s in cfg["sectors"]
        ]
        recompute_sectors(plan, cfg, polys)
        return True, None

    return False, "Unknown operation."


def _find_zone(cfg, sector_idx, zone_idx=None, zone_name=None):
    for s in cfg.get("sectors", []):
        if sector_idx is not None and s.get("idx") != sector_idx:
            continue
        for z in s.get("zones", []):
            if zone_idx is not None and z.get("idx") == zone_idx:
                return s, z
            if zone_name is not None and z.get("name") == zone_name:
                return s, z
    return None, None


def _rebuild_valves_pipes(plan, cfg):
    proj = plan["_proj"]
    principal_m, principal_ll = _principal_chain(plan, cfg, cfg.get("principal_order"))
    valves, majors, minors, zones_all = [], [], [], []
    for sector in cfg["sectors"]:
        entry_m = sector["entry_m"]
        entry_ll = proj.to_lonlat(entry_m)
        valves.append({
            "id": _valve_id("principal", sector["name"], sector["name"]),
            "kind": "principal", "sector": sector["name"], "zone": sector["name"],
            "diameter_mm": 90, "lon": entry_ll.x, "lat": entry_ll.y,
            "point": entry_ll, "name": "Valve principal {0}".format(sector["name"]),
        })
        for z in sector.get("zones", []):
            zone_m = z["poly_m"]
            valve_m = nearest_points(zone_m.boundary, Point(entry_m))[0]
            valve_ll = proj.to_lonlat(valve_m)
            tap_m = _nearest_on(principal_m, valve_m)
            major_m = LineString([tap_m, Point(valve_m)])
            target_m = zone_m.centroid
            tap2_m = _nearest_on(major_m, target_m)
            minor_m = LineString([tap2_m, target_m])
            z["centroid"] = proj.to_lonlat(target_m)
            valves.append({
                "id": _valve_id("secondary", sector["name"], z["name"]),
                "kind": "secondary", "sector": sector["name"], "zone": z["name"],
                "diameter_mm": 32, "lon": valve_ll.x, "lat": valve_ll.y,
                "point": valve_ll, "name": "Valve secondary {0}".format(z["name"]),
            })
            majors.append({"pid": "M:{0}".format(z["name"]),
                           "zone": z["name"], "sector": sector["name"], "diameter_mm": 63,
                           "line": proj.to_lonlat(major_m), "len_m": major_m.length})
            minors.append({"pid": "m:{0}".format(z["name"]),
                           "zone": z["name"], "sector": sector["name"], "diameter_mm": 32,
                           "line": proj.to_lonlat(minor_m), "len_m": minor_m.length})
            zones_all.append(z)
    cfg["zones"] = zones_all
    cfg["valves"] = valves
    cfg["pipes"] = {"principal": {"pid": "P", "diameter_mm": 90, "line": principal_ll,
                                  "len_m": principal_m.length},
                    "majors": majors, "minors": minors}
    cfg["ready"] = True
    _apply_valve_customization(plan, cfg)
    _number_valves(cfg)
    _apply_pipe_customization(plan, cfg)
    return cfg


def _valve_id(kind, sector, zone):
    if kind == "principal":
        return "P:{0}".format(sector)
    return "S:{0}".format(zone)


def _valve_key(v):
    return (v.get("kind"), v.get("sector"), v.get("zone"))


def _number_valves(cfg):
    """Name valves: principal ``S<idx>V1``, others ``S<idx>V11…``."""
    idx_of = {s.get("name"): s.get("idx") for s in cfg.get("sectors", [])}
    for v in cfg.get("valves") or []:
        if not v.get("custom") and v.get("kind") == "principal" and v.get("sector"):
            i = idx_of.get(v.get("sector"))
            if i is not None:
                v["name"] = "S{0}V1".format(i)
    counters = {}
    for v in cfg.get("valves") or []:
        if not v.get("custom") and v.get("kind") == "principal":
            continue
        sec = v.get("sector")
        i = idx_of.get(sec)
        if i is None:
            continue
        counters[sec] = max(counters.get(sec, 10), 10) + 1
        v["name"] = "S{0}V{1:d}".format(i, counters[sec])
    return cfg


def _apply_valve_customization(plan, cfg):
    """Re-apply manual valve edits on top of freshly rebuilt valves/pipes.

    Overrides/removals are keyed by (kind, sector, zone) so they survive the
    rebuilds triggered by sector/zone/basin edits. Stale keys (valves that no
    longer exist after a structural edit) are pruned. Moved secondary valves
    pull their 63 mm major and 32 mm minor pipes along; a moved principal
    valve is only a marker (the 90 mm principal still runs via entries).
    """
    proj = plan["_proj"]
    ov = cfg.get("valve_overrides") or {}
    removed = {tuple(r) for r in (cfg.get("removed_valves") or []) if r}
    pipes = cfg.get("pipes") or {}
    majors = {m.get("zone"): m for m in (pipes.get("majors") or [])}
    minors = {m.get("zone"): m for m in (pipes.get("minors") or [])}
    sectors = {s.get("name"): s for s in cfg.get("sectors", [])}
    zones = {z.get("name"): z for z in cfg.get("zones", [])}

    kept = []
    for v in cfg.get("valves") or []:
        key = _valve_key(v)
        if key in removed:
            if v.get("kind") != "principal":
                majors.pop(v.get("zone"), None)
                minors.pop(v.get("zone"), None)
            continue
        if key in ov:
            try:
                lon, lat = float(ov[key][0]), float(ov[key][1])
            except (TypeError, ValueError, IndexError):
                kept.append(v)
                continue
            v["lon"], v["lat"] = lon, lat
            v["point"] = Point(lon, lat)
            v["moved"] = True
            if v.get("kind") != "principal":
                sec = sectors.get(v.get("sector"))
                zon = zones.get(v.get("zone"))
                if sec is not None and zon is not None:
                    valve_m = proj.to_m(Point(lon, lat))
                    target_m = zon["poly_m"].centroid
                    princ_m, _ = _principal_chain(plan, cfg)
                    tap_m = _nearest_on(princ_m, valve_m)
                    major_m = LineString([tap_m, valve_m])
                    tap2_m = _nearest_on(major_m, target_m)
                    minor_m = LineString([tap2_m, target_m])
                    if v.get("zone") in majors:
                        majors[v["zone"]]["line"] = proj.to_lonlat(major_m)
                        majors[v["zone"]]["len_m"] = major_m.length
                    if v.get("zone") in minors:
                        minors[v["zone"]]["line"] = proj.to_lonlat(minor_m)
                        minors[v["zone"]]["len_m"] = minor_m.length
        kept.append(v)
    for c in cfg.get("custom_valves") or []:
        kept.append({
            "id": c.get("id"),
            "kind": c.get("kind"), "sector": c.get("sector"), "zone": c.get("zone"),
            "diameter_mm": c.get("diameter_mm", 32),
            "lon": c.get("lon"), "lat": c.get("lat"),
            "point": Point(c.get("lon"), c.get("lat")),
            "name": c.get("name"), "custom": True,
        })
    cfg["valves"] = kept
    pipes["majors"] = [majors[k] for k in list(majors)]
    pipes["minors"] = [minors[k] for k in list(minors)]

    alive = {_valve_key(v) for v in kept if not v.get("custom")}
    cfg["valve_overrides"] = {k: v for k, v in ov.items() if tuple(k) in alive}
    sec_names = {s.get("name") for s in cfg.get("sectors", [])}
    zon_names = {z.get("name") for z in cfg.get("zones", [])}
    still_there = []
    for r in removed:
        kind, sec, zon = tuple(r)
        if sec not in sec_names:
            continue
        if kind != "principal" and zon not in zon_names:
            continue
        still_there.append(list(r))
    cfg["removed_valves"] = still_there
    return cfg


def _zone_num(name):
    """Trailing Z number of a zone name (S1Z2 -> 2), else None."""
    m = _re.search(r"Z(\d+)\s*$", name or "")
    return int(m.group(1)) if m else None


def _rekey_sector(cfg, old, new):
    """Migrate valve keys after a sector rename (or one side of a swap).

    Auto zones are ``S<idx>Z<k>``, so a renamed sector's zone keys move to
    the sector's current index with the same trailing Z number.
    """
    sec = next((s for s in cfg.get("sectors", []) if s.get("name") == new), None)
    idx = sec.get("idx") if sec is not None else None

    def zone_map(zon):
        k = _zone_num(zon)
        if k is not None and idx is not None:
            return "S{0}Z{1:d}".format(idx, k)
        return zon

    ov = cfg.get("valve_overrides") or {}
    cfg["valve_overrides"] = {
        ((k[0], new, zone_map(k[2])) if k[1] == old else k): v
        for k, v in ov.items()
    }
    cfg["removed_valves"] = [
        ([r[0], new, zone_map(r[2])] if r[1] == old else r)
        for r in (cfg.get("removed_valves") or []) if r
    ]
    for c in cfg.get("custom_valves") or []:
        if c.get("sector") == old:
            c["sector"] = new
            c["zone"] = zone_map(c.get("zone"))
    return cfg


def _rekey_valves(cfg, old_sector=None, new_sector=None,
                  old_zone=None, new_zone=None, drop_sector=None):
    ov = cfg.get("valve_overrides") or {}
    removed = [tuple(r) for r in (cfg.get("removed_valves") or []) if r]
    customs = cfg.get("custom_valves") or []

    def swap_key(key):
        kind, sec, zon = tuple(key)
        if drop_sector is not None and sec == drop_sector:
            return None
        if old_sector is not None and sec == old_sector:
            sec = new_sector
        if old_zone is not None and zon == old_zone:
            zon = new_zone
        return (kind, sec, zon)

    cfg["valve_overrides"] = {swap_key(k): v for k, v in ov.items()
                              if swap_key(k) is not None}
    cfg["removed_valves"] = [list(swap_key(r)) for r in removed
                             if swap_key(r) is not None]
    for c in customs:
        if drop_sector is not None and c.get("sector") == drop_sector:
            c["sector"] = None
        elif old_sector is not None and c.get("sector") == old_sector:
            c["sector"] = new_sector
        if old_zone is not None and c.get("zone") == old_zone:
            c["zone"] = new_zone
    return cfg


def _pipe_pid(kind, zone):
    if kind == "principal":
        return "P"
    return ("M:" if kind == "major" else "m:") + str(zone)


def _ensure_pipe_pids(cfg):
    pipes = cfg.get("pipes") or {}
    if isinstance(pipes.get("principal"), dict):
        pipes["principal"].setdefault("pid", "P")
    for m in pipes.get("majors", []) or []:
        m.setdefault("pid", _pipe_pid("major", m.get("zone")))
    for m in pipes.get("minors", []) or []:
        m.setdefault("pid", _pipe_pid("minor", m.get("zone")))
    pipes.setdefault("customs", [])
    cfg.setdefault("pipe_overrides", {})
    cfg.setdefault("removed_pipes", [])
    cfg.setdefault("custom_pipes", [])
    return cfg


def _apply_pipe_customization(plan, cfg):
    """Re-apply manual pipe edits on top of freshly rebuilt piping.

    Geometry/diameter overrides live in ``pipe_overrides`` keyed by pipe id,
    removals in ``removed_pipes`` and added pipes in ``custom_pipes``; stale
    keys (zones gone after a structural edit) are pruned.
    """
    proj = plan["_proj"]
    pipes = cfg.get("pipes") or {}
    ov = cfg.get("pipe_overrides") or {}
    removed = {r for r in (cfg.get("removed_pipes") or []) if r}
    for key in ("majors", "minors"):
        kept = []
        for m in pipes.get(key, []) or []:
            if m.get("pid") in removed:
                continue
            o = ov.get(m.get("pid"))
            if o:
                if o.get("line"):
                    try:
                        pts = [(float(x), float(y)) for x, y in o["line"]]
                    except (TypeError, ValueError):
                        pts = []
                    if len(pts) >= 2:
                        line_ll = LineString(pts)
                        line_m = proj.to_m(line_ll)
                        m["line"] = line_ll
                        m["len_m"] = float(o.get("len_m", line_m.length))
                if o.get("diameter_mm"):
                    try:
                        m["diameter_mm"] = int(o["diameter_mm"])
                    except (TypeError, ValueError):
                        pass
            kept.append(m)
        pipes[key] = kept
    customs = []
    for c in cfg.get("custom_pipes") or []:
        try:
            line_ll = c["line"] if hasattr(c.get("line"), "geom_type") else LineString(
                [(float(x), float(y)) for x, y in c.get("line")])
        except (TypeError, ValueError, KeyError):
            continue
        customs.append({"pid": c.get("id"), "zone": c.get("zone"),
                        "sector": c.get("sector"),
                        "diameter_mm": c.get("diameter_mm", 32),
                        "line": line_ll, "len_m": c.get("len_m", 0.0),
                        "custom": True})
    pipes["customs"] = customs
    alive = {m.get("pid") for m in (pipes.get("majors", []) or [])
             + (pipes.get("minors", []) or [])}
    cfg["pipe_overrides"] = {k: v for k, v in ov.items() if k in alive}
    cfg["removed_pipes"] = sorted(removed & alive)
    return cfg


def _rekey_pipe_zone(cfg, old, new):
    def swap(pid):
        if pid == "M:" + old:
            return "M:" + new
        if pid == "m:" + old:
            return "m:" + new
        return pid
    cfg["pipe_overrides"] = {swap(k): v for k, v in (cfg.get("pipe_overrides") or {}).items()}
    cfg["removed_pipes"] = [swap(r) for r in (cfg.get("removed_pipes") or []) if r]
    for c in cfg.get("custom_pipes") or []:
        if c.get("zone") == old:
            c["zone"] = new
    return cfg


def _rekey_pipe_sector(cfg, old, new):
    sec = next((s for s in cfg.get("sectors", []) if s.get("name") == new), None)
    idx = sec.get("idx") if sec is not None else None
    zsec = {}
    for s in cfg.get("sectors", []):
        for z in s.get("zones", []) or []:
            zsec[z.get("name")] = s.get("name")

    def zone_map(zon):
        k = _zone_num(zon)
        if k is not None and idx is not None:
            return "S{0}Z{1:d}".format(idx, k)
        return zon

    def swap(pid):
        for pre in ("M:", "m:"):
            if pid.startswith(pre) and zsec.get(pid[len(pre):]) == old:
                return pre + zone_map(pid[len(pre):])
        return pid
    cfg["pipe_overrides"] = {swap(k): v for k, v in (cfg.get("pipe_overrides") or {}).items()}
    cfg["removed_pipes"] = [swap(r) for r in (cfg.get("removed_pipes") or []) if r]
    for c in cfg.get("custom_pipes") or []:
        if c.get("sector") == old:
            c["sector"] = new
            c["zone"] = zone_map(c.get("zone"))
    return cfg


def apply_valve_op(plan, cfg, op, valve_id=None, kind=None,
                   lon=None, lat=None, sector=None, zone=None):
    """Add / move / remove a valve. Returns (ok, message).

    Derived valves (one principal 90 mm per sector, one secondary 32 mm per
    zone) keep their automatic placement unless moved: the new position is
    stored in ``valve_overrides`` and re-applied after every rebuild, with
    the 63/32 mm pipes following moved secondary valves. Added valves are
    stored in ``custom_valves`` (markers only, no pipes).
    """
    if op == "confirm":
        cfg["valves_confirmed"] = True
        return True, None
    if op == "move":
        v = next((x for x in cfg.get("valves", []) if x.get("id") == valve_id), None)
        if v is None:
            return False, "Valve not found."
        try:
            lon_f, lat_f = float(lon), float(lat)
        except (TypeError, ValueError):
            return False, "Invalid coordinates."
        if plan["_land_m"].distance(plan["_proj"].to_m(Point(lon_f, lat_f))) > 1.0:
            return False, "The valve must lie inside the land boundary."
        if v.get("custom"):
            for c in cfg.get("custom_valves") or []:
                if c.get("id") == valve_id:
                    c["lon"], c["lat"] = lon_f, lat_f
        else:
            cfg.setdefault("valve_overrides", {})[_valve_key(v)] = [lon_f, lat_f]
        _rebuild_valves_pipes(plan, cfg)
        cfg["valves_confirmed"] = False
        return True, None

    if op == "add":
        kind = (kind or "secondary").strip()
        if kind not in ("principal", "secondary"):
            kind = "secondary"
        sec = next((s for s in cfg.get("sectors", []) if s.get("name") == sector), None)
        if sec is None:
            return False, "Sector not found."
        zon_name = None
        if kind == "secondary":
            zon = next((z for z in sec.get("zones", []) if z.get("name") == zone), None)
            if zon is None:
                return False, "Zone not found."
            zon_name = zon["name"]
        try:
            lon_f, lat_f = float(lon), float(lat)
        except (TypeError, ValueError):
            return False, "Invalid coordinates."
        if plan["_land_m"].distance(plan["_proj"].to_m(Point(lon_f, lat_f))) > 1.0:
            return False, "The valve must lie inside the land boundary."
        vid = "C:{0}".format(_uuid.uuid4().hex[:8])
        label = zon_name or sec["name"]
        cfg.setdefault("custom_valves", []).append({
            "id": vid, "kind": kind, "sector": sec["name"], "zone": label,
            "diameter_mm": 90 if kind == "principal" else 32,
            "lon": lon_f, "lat": lat_f,
            "name": "Valve {0} {1}".format(kind, label),
        })
        _rebuild_valves_pipes(plan, cfg)
        cfg["valves_confirmed"] = False
        return True, None

    if op == "remove":
        v = next((x for x in cfg.get("valves", []) if x.get("id") == valve_id), None)
        if v is None:
            return False, "Valve not found."
        if v.get("custom"):
            cfg["custom_valves"] = [c for c in (cfg.get("custom_valves") or [])
                                    if c.get("id") != valve_id]
        else:
            key = _valve_key(v)
            cfg.setdefault("removed_valves", []).append(list(key))
            (cfg.get("valve_overrides") or {}).pop(key, None)
        _rebuild_valves_pipes(plan, cfg)
        cfg["valves_confirmed"] = False
        return True, None

    return False, "Unknown operation."


def _pipe_line_m(plan, path):
    """Validate an lon/lat path inside the land; returns (line_ll, len_m)."""
    try:
        pts = [(float(x), float(y)) for x, y in path]
    except (TypeError, ValueError):
        return None, "Invalid coordinates."
    if len(pts) < 2:
        return None, "Invalid coordinates."
    line_ll = LineString(pts)
    line_m = plan["_proj"].to_m(line_ll)
    if line_m.length < 1.0:
        return None, "Invalid coordinates."
    for x, y in pts:
        if plan["_land_m"].distance(plan["_proj"].to_m(Point(x, y))) > 1.0:
            return None, "The pipe must lie inside the land boundary."
    return (line_ll, line_m.length), None


def _find_pipe(cfg, pid):
    pipes = cfg.get("pipes") or {}
    if (pipes.get("principal") or {}).get("pid") == pid:
        return pipes["principal"]
    for m in (pipes.get("majors", []) or []) + (pipes.get("minors", []) or []):
        if m.get("pid") == pid:
            return m
    for m in pipes.get("customs", []) or []:
        if m.get("pid") == pid:
            return m
    return None


def _pipe_totals(cfg):
    pipes = cfg.get("pipes") or {}
    princ = (pipes.get("principal") or {}).get("len_m", 0.0)
    majors = sum(m.get("len_m", 0.0) for m in pipes.get("majors", []) or [])
    minors = sum(m.get("len_m", 0.0) for m in pipes.get("minors", []) or [])
    customs = sum(m.get("len_m", 0.0) for m in pipes.get("customs", []) or [])
    return princ, majors + minors + customs, princ + majors + minors + customs


def optimize_pipes(plan, cfg):
    """AI optimal trace: shortest principal visit order, closest taps.

    Orders the principal 90 mm chain greedily (nearest entry next) from the
    basin, then rebuilds every 63/32 mm pipe from its closest tap point.
    Stores the visit order for future rebuilds plus a savings report.
    """
    before_p, _, before_t = _pipe_totals(cfg)
    remaining = [(s.get("name"), s["entry_m"]) for s in cfg.get("sectors", [])]
    order, cur = [], plan["_basin_m"]
    while remaining:
        i = min(range(len(remaining)), key=lambda k: remaining[k][1].distance(cur))
        name, pt = remaining.pop(i)
        order.append(name)
        cur = pt
    cfg["principal_order"] = order
    _rebuild_valves_pipes(plan, cfg)
    after_p, _, after_t = _pipe_totals(cfg)
    saved = max(0.0, before_t - after_t)
    cfg["pipe_report"] = {
        "principal_before": round(before_p, 1),
        "principal_after": round(after_p, 1),
        "total_before": round(before_t, 1),
        "total_after": round(after_t, 1),
        "saved_m": round(saved, 1),
        "saved_pct": round(100.0 * saved / before_t, 1) if before_t > 0 else 0.0,
        "order": list(order),
    }
    return True, cfg["pipe_report"]


def apply_pipe_op(plan, cfg, op, pipe_id=None, diameter=None,
                  sector=None, zone=None, path=None):
    """Add / change / remove a pipe. Returns (ok, message).

    Derived pipes (principal 90 mm, majors 63 mm, minors 32 mm) keep their
    automatic geometry unless changed: the new line/diameter is stored in
    ``pipe_overrides`` and re-applied after every rebuild. Removed derived
    pipes (majors/minors only) are stored in ``removed_pipes``. Added pipes
    are stored in ``custom_pipes`` (straight 2-point segments).
    """
    if op == "change":
        target = _find_pipe(cfg, pipe_id)
        if target is None:
            return False, "Pipe not found."
        try:
            diam = int(diameter) if diameter not in (None, "") else None
        except (TypeError, ValueError):
            return False, "Invalid diameter."
        if diam is not None and diam not in (90, 63, 32):
            diam = 32 if target.get("pid", "").startswith("m:") else (
                63 if target.get("pid", "").startswith("M:") else 90)
        new_line, new_len = None, None
        if path:
            (res, err) = _pipe_line_m(plan, path)
            if err:
                return False, err
            new_line, new_len = res
        if target.get("custom"):
            for c in cfg.get("custom_pipes") or []:
                if c.get("id") == pipe_id:
                    if new_line is not None:
                        c["line"] = new_line
                        c["len_m"] = new_len
                    if diam is not None:
                        c["diameter_mm"] = diam
        else:
            if target.get("pid") == "P" and new_line is None and diam is None:
                return False, "Nothing to change."
            ov = cfg.setdefault("pipe_overrides", {}).setdefault(target["pid"], {})
            if new_line is not None:
                ov["line"] = [[round(float(x), 6), round(float(y), 6)]
                              for x, y in new_line.coords]
                ov["len_m"] = new_len
            if diam is not None:
                ov["diameter_mm"] = diam
        _rebuild_valves_pipes(plan, cfg)
        return True, None

    if op == "add":
        try:
            diam = int(diameter)
        except (TypeError, ValueError):
            diam = 32
        if diam not in (90, 63, 32):
            diam = 32
        kind = {90: "principal", 63: "major", 32: "minor"}[diam]
        sec = next((s for s in cfg.get("sectors", []) if s.get("name") == sector), None)
        if sec is None:
            return False, "Sector not found."
        zon_name = None
        if kind != "principal":
            zon = next((z for z in sec.get("zones", []) if z.get("name") == zone), None)
            if zon is None:
                return False, "Zone not found."
            zon_name = zon["name"]
        (res, err) = _pipe_line_m(plan, path)
        if err:
            return False, err
        new_line, new_len = res
        cfg.setdefault("custom_pipes", []).append({
            "id": "C:{0}".format(_uuid.uuid4().hex[:8]), "kind": kind,
            "sector": sec["name"], "zone": zon_name or sec["name"],
            "diameter_mm": diam, "line": new_line, "len_m": new_len,
        })
        _rebuild_valves_pipes(plan, cfg)
        return True, None

    if op == "remove":
        target = _find_pipe(cfg, pipe_id)
        if target is None:
            return False, "Pipe not found."
        if target.get("pid") == "P" and not target.get("custom"):
            return False, "Cannot remove the principal pipe."
        if target.get("custom"):
            cfg["custom_pipes"] = [c for c in (cfg.get("custom_pipes") or [])
                                   if c.get("id") != pipe_id]
        else:
            cfg.setdefault("removed_pipes", []).append(target["pid"])
        _rebuild_valves_pipes(plan, cfg)
        return True, None

    return False, "Unknown operation."


def _idw_z(pts_m, p):
    num, den = 0.0, 0.0
    for q, z in pts_m:
        d = p.distance(q)
        if d < 1e-6:
            return z
        w = 1.0 / (d * d)
        num += w * z
        den += w
    return num / den if den > 0 else 0.0


def _zone_row_fit(pts_m, zone_m):
    """Fit a plane over IDW-interpolated samples inside the zone.

    Returns (row_angle, slope_pct) with rows running along the contour
    (perpendicular to the steepest descent), or None without elevation data.
    """
    minx, miny, maxx, maxy = zone_m.bounds
    samples = [zone_m.centroid]
    n = 6
    for i in range(n):
        for j in range(n):
            p = Point(minx + (maxx - minx) * (i + 0.5) / n,
                      miny + (maxy - miny) * (j + 0.5) / n)
            if zone_m.intersects(p):
                samples.append(p)
    seen, uniq = set(), []
    for p in samples:
        k = (round(p.x, 3), round(p.y, 3))
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    if len(uniq) < 4:
        return None
    xyz = [(p.x, p.y, _idw_z(pts_m, p)) for p in uniq]
    mx = sum(s[0] for s in xyz) / len(xyz)
    my = sum(s[1] for s in xyz) / len(xyz)
    sxx = syy = sxy = sxz = syz = 0.0
    for x, y, z in xyz:
        dx, dy = x - mx, y - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
        sxz += dx * z
        syz += dy * z
    den = sxx * syy - sxy * sxy
    if den <= 1e-9 * sxx * syy:
        return None
    a = (sxz * syy - syz * sxy) / den
    b = (syz * sxx - sxz * sxy) / den
    slope = _math.hypot(a, b) * 100.0
    if slope < 1e-9:
        return main_axis_angle(zone_m) % 180.0, 0.0
    grad = _math.degrees(_math.atan2(b, a))
    return (grad + 90.0) % 180.0, round(slope, 1)


def _trace_rows(zone_m, angle, spacing):
    """Parallel row segments across the zone, spaced `spacing` metres apart."""
    origin = zone_m.centroid
    fwd, inv = _affine_params(angle, origin)
    fp = _affine(zone_m, fwd)
    if fp.is_empty:
        return []
    xmin, ymin, xmax, ymax = fp.bounds
    ext = max(xmax - xmin, ymax - ymin) + spacing
    rows = []
    y = ymin + spacing / 2.0
    while y <= ymax and len(rows) < 2000:
        a = _affine(Point(xmin - ext, y), inv)
        b = _affine(Point(xmax + ext, y), inv)
        inter = zone_m.intersection(LineString([(a.x, a.y), (b.x, b.y)]))
        if inter.is_empty:
            y += spacing
            continue
        if inter.geom_type == "LineString":
            parts = [inter]
        elif inter.geom_type == "MultiLineString":
            parts = list(inter.geoms)
        else:
            parts = [g for g in getattr(inter, "geoms", []) if g.geom_type == "LineString"]
        for g in parts:
            if g.length >= 2.0:
                rows.append(g)
        y += spacing
    return rows


def _compute_zone_rows(plan, pts_m, z, spacing):
    proj = plan["_proj"]
    zone_m = z.get("poly_m")
    fit = _zone_row_fit(pts_m, zone_m) if len(pts_m) >= 3 and zone_m is not None else None
    manual = z.get("rows_manual")
    if manual is not None:
        try:
            angle = float(manual) % 180.0
        except (TypeError, ValueError):
            angle = None
        if angle is None:
            manual = None
    else:
        angle = None
    if fit is None:
        auto, slope, elev = main_axis_angle(zone_m) % 180.0, 0.0, False
    else:
        auto, slope, elev = fit[0], fit[1], True
    if angle is None:
        angle = auto
    lines_m = _trace_rows(zone_m, angle, spacing)
    z["rows"] = {"angle": round(angle, 1), "spacing_m": spacing,
                 "slope_pct": slope, "has_elev": elev,
                 "manual": manual is not None,
                 "n": len(lines_m),
                 "total_m": round(sum(g.length for g in lines_m), 1),
                 "lines": [proj.to_lonlat(g) for g in lines_m]}
    return z["rows"]


def compute_rows(plan, cfg, spacing=None):
    """AI row tracing: contour-following rows per zone from the elevation.

    Direction comes from a least-squares slope fit over IDW-interpolated
    KML altitudes; without elevation data rows follow the zone long axis.
    """
    if spacing is None:
        spacing = cfg.get("row_spacing", ROW_SPACING_DEFAULT)
    try:
        spacing = float(spacing)
    except (TypeError, ValueError):
        spacing = ROW_SPACING_DEFAULT
    spacing = max(ROW_SPACING_MIN, min(ROW_SPACING_MAX, spacing))
    proj = plan["_proj"]
    raw = [(lon, lat, z) for lon, lat, z in (plan.get("vertices_z") or [])
           if z not in (None, 0)]
    pts_m = [(proj.to_m(Point(lon, lat)), z) for lon, lat, z in raw]
    for sector in cfg.get("sectors", []):
        for z in sector.get("zones", []):
            _compute_zone_rows(plan, pts_m, z, spacing)
    cfg["row_spacing"] = spacing
    return cfg


def apply_rows_op(plan, cfg, spacing=None):
    try:
        sp = float(spacing)
    except (TypeError, ValueError):
        return False, "Invalid spacing."
    if not (ROW_SPACING_MIN <= sp <= ROW_SPACING_MAX):
        return False, "Invalid spacing."
    compute_rows(plan, cfg, sp)
    cfg["rows_confirmed"] = False
    return True, None


def apply_row_direction(plan, cfg, sector_idx=None, zone_name=None, angle=None):
    """Set a manual row direction for one zone and re-trace it."""
    sector = next((s for s in cfg.get("sectors", []) if s.get("idx") == sector_idx), None)
    if sector is None:
        return False, "Sector not found."
    target = next((z for z in sector.get("zones", []) if z.get("name") == zone_name), None)
    if target is None:
        return False, "Zone not found."
    try:
        ang = float(angle)
    except (TypeError, ValueError):
        return False, "Invalid angle."
    proj = plan["_proj"]
    raw = [(lon, lat, z) for lon, lat, z in (plan.get("vertices_z") or [])
           if z not in (None, 0)]
    pts_m = [(proj.to_m(Point(lon, lat)), z) for lon, lat, z in raw]
    target["rows_manual"] = round(ang % 180.0, 1)
    spacing = cfg.get("row_spacing", ROW_SPACING_DEFAULT)
    _compute_zone_rows(plan, pts_m, target, spacing)
    cfg["rows_confirmed"] = False
    return True, None


def apply_tree_op(plan, cfg, trees):
    """Set tree type, spacing and coverage of zones. Returns (ok, message).

    ``trees`` maps zone names to a tree-type key or to
    ``{tree, dist, pct}``; every zone keeps its own values so layouts can
    be mixed. Tree count assumes a square grid: floor(area*pct/100/dist²).
    """
    if not isinstance(trees, dict):
        return False, "Invalid tree selection."
    zones = {z.get("name"): z for s in cfg.get("sectors", [])
             for z in (s.get("zones", []) or [])}
    for zone_name, spec in trees.items():
        if isinstance(spec, str):
            spec = {"tree": spec}
        if not isinstance(spec, dict):
            return False, "Invalid tree selection."
        tree = spec.get("tree", "none")
        if tree not in TREE_TYPES:
            return False, "Invalid tree selection."
        try:
            dist = float(spec.get("dist", TREE_DIST_DEFAULT))
        except (TypeError, ValueError):
            return False, "Invalid tree spacing."
        if not (TREE_DIST_MIN <= dist <= TREE_DIST_MAX):
            return False, "Invalid tree spacing."
        try:
            pct = float(spec.get("pct", 100.0))
        except (TypeError, ValueError):
            return False, "Invalid tree percentage."
        if not (0.0 <= pct <= 100.0):
            return False, "Invalid tree percentage."
        target = zones.get(zone_name)
        if target is None:
            return False, "Zone not found."
        target["tree"] = tree
        target["tree_dist"] = dist
        target["tree_pct"] = pct
    return True, None


def tree_stats(zone):
    """Planted area and tree count for a zone (square-grid spacing)."""
    area = zone.get("area_m2") or 0.0
    dist = zone.get("tree_dist")
    if dist is None:
        dist = TREE_DIST_DEFAULT
    pct = zone.get("tree_pct")
    if pct is None:
        pct = 100.0
    planted = area * pct / 100.0
    try:
        n = int(planted // (dist * dist)) if dist > 0 else 0
    except (TypeError, ValueError):
        n = 0
    return {"dist": dist, "pct": pct, "planted_m2": round(planted, 1), "n": n}


def _move_zone_refs(cfg, old, new):
    for v in cfg.get("valves", []):
        if v.get("zone") == old:
            v["zone"] = new
    for m in (cfg.get("pipes", {}).get("majors", []) + cfg.get("pipes", {}).get("minors", [])):
        if m.get("zone") == old:
            m["zone"] = new
    _rekey_valves(cfg, old_zone=old, new_zone=new)
    _rekey_pipe_zone(cfg, old, new)


def apply_zone_op(plan, cfg, op, sector_idx=None, zone_idx=None, zone_name=None,
                  name=None, x1=None, y1=None, x2=None, y2=None,
                  zone_name2=None, zone_names=None):
    proj = plan["_proj"]
    sector = next((s for s in cfg.get("sectors", []) if s.get("idx") == sector_idx), None)
    if sector is None:
        return False, "Sector not found."
    zones = sector.get("zones", [])
    if op == "rename":
        nm = (name or "").strip()
        if not nm:
            return False, "Empty zone name."
        taken = {z.get("name", "").lower() for z in cfg.get("zones", [])
                 if z.get("name") != (zone_name or "")}
        if nm.lower() in taken:
            return False, "That zone name is already used. Pick a unique name."
        target = next((z for z in zones if z.get("name") == zone_name), None)
        if target is None and zone_idx is not None:
            target = next((z for z in zones if z.get("idx") == zone_idx), None)
        if target is None:
            return False, "Zone not found."
        old = target["name"]
        target["name"] = nm
        _move_zone_refs(cfg, old, nm)
        _rebuild_valves_pipes(plan, cfg)
        cfg["zones_confirmed"] = False
        cfg["rows_confirmed"] = False
        cfg["valves_confirmed"] = False
        return True, None
    if op == "swap":
        a = next((z for z in zones if z.get("name") == zone_name), None)
        b = next((z for z in zones if z.get("name") == zone_name2), None)
        if a is None or b is None or zone_name == zone_name2:
            return False, "Select two zones to swap."
        tmp = "__swap_tmp__"
        while tmp.lower() in {z.get("name", "").lower() for z in cfg.get("zones", [])}:
            tmp = "_" + tmp
        old_a, old_b = a["name"], b["name"]
        a["name"] = tmp
        _move_zone_refs(cfg, old_a, tmp)
        b["name"] = old_a
        _move_zone_refs(cfg, old_b, old_a)
        a["name"] = old_b
        _move_zone_refs(cfg, tmp, old_b)
        _rebuild_valves_pipes(plan, cfg)
        cfg["zones_confirmed"] = False
        cfg["rows_confirmed"] = False
        cfg["valves_confirmed"] = False
        return True, None
    if op == "merge":
        wanted = {n for n in (zone_names or []) if n}
        if zone_name:
            wanted.add(zone_name)
        targets = [z for z in zones if z.get("name") in wanted]
        if len(targets) < 2:
            return False, "Select two zones to merge."
        survivor = min(targets, key=lambda z: z.get("idx", 0))
        merged = survivor["poly_m"]
        for z in targets:
            if z is not survivor:
                merged = merged.union(z["poly_m"])
        if not merged.is_valid:
            merged = make_valid(merged)
        sector["zones"] = [z for z in zones if z is survivor or z not in targets]
        survivor["poly_m"] = merged
        survivor["poly"] = proj.to_lonlat(merged)
        survivor["area_m2"] = merged.area
        for i, z in enumerate(sorted(sector["zones"], key=lambda z: z.get("idx", 0)), start=1):
            z["idx"] = i
            z["name"] = "S{0}Z{1:d}".format(sector["idx"], i)
        _rebuild_valves_pipes(plan, cfg)
        cfg["zones_confirmed"] = False
        cfg["rows_confirmed"] = False
        cfg["valves_confirmed"] = False
        return True, None
    if op == "remove":
        wanted = {n for n in (zone_names or []) if n}
        if zone_name:
            wanted.add(zone_name)
        targets = [z for z in zones if z.get("name") in wanted]
        if not targets and zone_idx is not None:
            targets = [z for z in zones if z.get("idx") == zone_idx]
        if not targets:
            return False, "Zone not found."
        rest = [z for z in zones if z not in targets]
        if not rest:
            return False, "Cannot remove the last zone."
        merged = rest[0]["poly_m"]
        for z in targets:
            merged = merged.union(z["poly_m"])
        if not merged.is_valid:
            merged = make_valid(merged)
        rest[0]["poly_m"] = merged
        rest[0]["poly"] = proj.to_lonlat(merged)
        rest[0]["area_m2"] = merged.area
        sector["zones"] = rest
        for i, z in enumerate(sorted(rest, key=lambda z: z.get("idx", 0)), start=1):
            z["idx"] = i
            z["name"] = "S{0}Z{1:d}".format(sector["idx"], i)
        _rebuild_valves_pipes(plan, cfg)
        cfg["zones_confirmed"] = False
        cfg["rows_confirmed"] = False
        cfg["valves_confirmed"] = False
        return True, None
    if op == "split":
        try:
            a = proj.to_m(Point(float(x1), float(y1)))
            b = proj.to_m(Point(float(x2), float(y2)))
        except (TypeError, ValueError):
            return False, "Invalid coordinates."
        if a.distance(b) < 1.0:
            return False, "Invalid coordinates."
        target = next((z for z in zones if z.get("name") == zone_name), None)
        if target is None and zone_idx is not None:
            target = next((z for z in zones if z.get("idx") == zone_idx), None)
        if target is None:
            target = max(zones, key=lambda z: z.get("area_m2", 0)) if zones else None
        if target is None:
            return False, "Zone not found."
        zm = target["poly_m"]
        dx, dy = b.x - a.x, b.y - a.y
        L = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / L, dy / L
        ext = max(zm.bounds[2] - zm.bounds[0], zm.bounds[3] - zm.bounds[1]) + 100.0
        line = LineString([(a.x - ux * ext, a.y - uy * ext), (b.x + ux * ext, b.y + uy * ext)])
        try:
            res = _shapely_split(zm, line)
        except Exception:  # noqa: BLE001 - degenerate split
            return False, "Invalid polygon."
        parts = [g for g in res.geoms if g.geom_type.startswith("Polygon") and g.area > 60.0]
        if len(parts) < 2:
            return False, "The line must cross the zone."
        parts.sort(key=lambda g: g.area, reverse=True)
        keep = parts[:2]
        rest = [z for z in zones if z is not target]
        new_zones = []
        for g in keep:
            if not g.is_valid:
                g = make_valid(g)
            new_zones.append({"poly_m": g, "poly": proj.to_lonlat(g), "area_m2": g.area,
                              "centroid": proj.to_lonlat(g.centroid), "tree": "none",
                              "tree_dist": TREE_DIST_DEFAULT, "tree_pct": 100.0})
        sector["zones"] = rest + new_zones
        for i, z in enumerate(sector["zones"], start=1):
            z["idx"] = i
            z["name"] = "S{0}Z{1:d}".format(sector["idx"], i)
        _rebuild_valves_pipes(plan, cfg)
        cfg["zones_confirmed"] = False
        cfg["rows_confirmed"] = False
        cfg["valves_confirmed"] = False
        return True, None
    if op == "confirm":
        cfg["zones_confirmed"] = True
        _rebuild_valves_pipes(plan, cfg)
        return True, None
    return False, "Unknown operation."


def analyse_other_element(plan, cfg, kind, lon, lat):
    proj = plan["_proj"]
    try:
        pt_m = proj.to_m(Point(float(lon), float(lat)))
    except (TypeError, ValueError):
        return {"necessary": False, "verdict": "Invalid coordinates.", "suggestion": ""}
    inside = plan["_land_m"].contains(pt_m) or plan["_land_m"].distance(pt_m) < 1.0
    if not inside:
        return {"necessary": False, "verdict": "Outside the land boundary - move it inside.",
                "suggestion": "Pick a point inside the land, close to a pipe, to avoid extra trenching."}
    best = 1e18
    for s in cfg.get("sectors", []):
        try:
            best = min(best, s["poly_m"].distance(pt_m))
        except Exception:  # noqa: BLE001 - display-only
            continue
    for m in (cfg.get("pipes", {}).get("majors", []) or []) + (cfg.get("pipes", {}).get("minors", []) or []) + (cfg.get("pipes", {}).get("customs", []) or []):
        try:
            best = min(best, proj.to_m(m["line"]).distance(pt_m))
        except Exception:  # noqa: BLE001 - display-only
            continue
    basin_d = pt_m.distance(plan["_basin_m"])
    if kind == "pressure_reducer":
        necessary = basin_d < 120.0 or (plan.get("basin") or {}).get("has_elev")
        verdict = "Useful near the basin / high point to protect 32 mm lines." if necessary else \
            "Probably unnecessary this far from the basin - pressure is already low."
        suggestion = "Keep one reducer just after the basin; add a second only if a zone sits >15 m below the basin. This keeps the network smooth and cheap."
    elif kind in ("connector_90_63", "connector_63_32"):
        necessary = best < 60.0
        verdict = "Necessary transition where pipe size changes." if necessary else \
            "Too far from any pipe - move it onto the line to avoid extra fittings."
        suggestion = "Prefer a single 90x63 reducer at each sector entry and 63x32 at each zone valve; fewer fittings = less head loss and lower cost."
    elif kind in ("tee_63", "elbow_63", "elbow_32"):
        necessary = best < 40.0
        verdict = "Handy to smooth a sharp angle." if necessary else \
            "Not needed here - no pipe bend nearby."
        suggestion = "Replace two 90-degree elbows with one 45-degree sweep where possible; it cuts friction and is cheaper long-term."
    elif kind == "filter_90":
        necessary = basin_d < 60.0
        verdict = "Recommended just after the basin." if necessary else \
            "A filter belongs at the head, not deep in the field."
        suggestion = "One 120-mesh filter at the head + small screen at each sector valve is the cheapest reliable combo."
    elif kind == "pump_booster":
        necessary = basin_d > 250.0 or best > 80.0
        verdict = "Consider only for far / uphill zones." if necessary else \
            "Probably overkill - gravity + head from the basin should suffice."
        suggestion = "Before buying a booster, try shortening the principal line or raising the basin; a booster adds energy cost every year."
    else:
        necessary = best < 60.0
        verdict = "Placed near the network." if necessary else "Far from the network."
        suggestion = "Group fittings along the principal line to shorten trenches and share labour."
    return {"necessary": bool(necessary), "verdict": verdict, "suggestion": suggestion}


def compute_simulation(plan, cfg, years=10, capex=0.0, annual_cost=0.0,
                       annual_revenue=0.0, crop="vegetables"):
    try:
        years = max(1, min(30, int(years)))
    except (TypeError, ValueError):
        years = 10
    try:
        capex, annual_cost, annual_revenue = float(capex), float(annual_cost), float(annual_revenue)
    except (TypeError, ValueError):
        capex, annual_cost, annual_revenue = 0.0, 0.0, 0.0
    area_ha = (plan.get("land_area_m2") or 0.0) / 10000.0
    rows = []
    cum = -capex
    breakeven = None
    for y in range(1, years + 1):
        net = annual_revenue - annual_cost
        cum += net
        roi = (cum / capex * 100.0) if capex > 0 else 0.0
        rows.append({"year": y, "net": round(net, 2), "cumulative": round(cum, 2),
                     "roi_pct": round(roi, 1)})
        if breakeven is None and cum >= 0:
            breakeven = y
    crop_hint = {
        "vegetables": "Short-cycle vegetables: fast cash, needs steady water and labour.",
        "fruits": "Orchard / drip fruits: higher capex, best ROI after year 3-4, low headache once set.",
        "cereals": "Cereals: low margin, only pays on large areas with mechanisation.",
        "fodder": "Fodder + small livestock: stable income, modest water use.",
    }.get(crop, "")
    ai = ai_proposal(plan, cfg, crop)
    return {"years": years, "area_ha": round(area_ha, 2), "capex": capex,
            "annual_cost": annual_cost, "annual_revenue": annual_revenue,
            "crop": crop, "crop_hint": crop_hint, "rows": rows,
            "breakeven_year": breakeven,
            "total_net": round(cum + capex, 2) if rows else 0.0,
            "ai": ai}


def ai_proposal(plan, cfg, crop="vegetables"):
    area_ha = (plan.get("land_area_m2") or 0.0) / 10000.0
    n_sec = len(cfg.get("sectors", [])) if cfg else 0
    pipe_m = 0.0
    if cfg and cfg.get("pipes"):
        pipe_m = (cfg["pipes"]["principal"]["len_m"]
                  + sum(m["len_m"] for m in cfg["pipes"].get("majors", []))
                  + sum(m["len_m"] for m in cfg["pipes"].get("minors", []))
                  + sum(m["len_m"] for m in cfg["pipes"].get("customs", [])))
    if area_ha < 1.0:
        plan_txt = ("Keep {0} sectors on drip with mulch; grow two vegetable cycles + one "
                    "legume to cut fertiliser cost. Add a small farm-gate stand - direct "
                    "sale doubles margin with almost no extra work.".format(max(n_sec, 1)))
    elif area_ha < 5.0:
        plan_txt = ("Drip everywhere, one filter station, mulch; split the farm: 60% high-value "
                    "vegetables, 30% orchard (olive/pomegranate, low water, low headache), 10% "
                    "fodder for a few sheep. Solar pump kills the energy bill.")
    else:
        plan_txt = ("Mechanised drip + soil probes; 50% orchard under drip (best ROI/ha with "
                    "little labour), 30% seasonal vegetables near the basin (short pipes = cheap), "
                    "20% cereals/fodder for rotation. One worker + seasonal help is enough.")
    saving = ("Shorten majors by grouping zone valves along the sector entry line; every 100 m "
              "of 63 mm saved is ~fittings + trench labour avoided. Prefer 45-degree sweeps over "
              "90-degree elbows to cut pumping head.")
    return {"plan": plan_txt,
            "pipe_m": round(pipe_m, 1),
            "income_idea": "Grade + pack on site and sell weekly boxes; a tiny cold corner lets you hold prices.",
            "headache": "Drip + timer + filter = 30 min/day. Avoid sprinklers and thirsty summer crops unless water is free.",
            "saving": saving}