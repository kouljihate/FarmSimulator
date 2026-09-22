"""The planning engine.

Pipeline (this first part):
  1. basin   -> best spot near the water point, at a favourable elevation
  2. sectorisation -> up to 5 config maps of the land split into sectors <= 10000 m2
  3. zonage  -> every sector split into 3 equal-area zones (Z1, Z2, Z3)
  4. valves  -> one 50 mm valve at the first point of each zone
  5. piping  -> 90 mm principal, 50 mm majors, 32 mm minors
"""
import re as _re

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, unary_union
from shapely.validation import make_valid

from .geo import Projector, main_axis_angle, sweep_split
from .sector import partition

MAX_SECTOR_AREA = 10000.0
N_ZONES = 3
MIN_EXISTING_COVERAGE = 0.5  # sectors already in the file must cover >= 50% of the land


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


def extend_config(plan, project, cfg, basin_m, max_elev_m):
    """Add zones, valves and pipes to a chosen sectorisation config."""
    if cfg.get("ready"):
        return cfg

    principal_pts = []
    if max_elev_m is not None:
        principal_pts.append(max_elev_m)
    principal_pts.append(basin_m)
    for s in cfg["sectors"]:
        principal_pts.append(s["entry_m"])

    principal_m = LineString(principal_pts)
    principal_ll = project.to_lonlat(principal_m)

    zones_all = []
    valves = []
    majors = []
    minors = []

    for sector in cfg["sectors"]:
        sector_m = sector["poly_m"]
        scan_angle = sector.get("zone_angle", cfg["angle"] + 90.0)
        pieces = sweep_split(sector_m, scan_angle, N_ZONES)
        order = _zone_order(sector, pieces, basin_m, scan_angle)

        zidx = 0
        for pi in order:
            zone_m = pieces[pi]
            if zone_m is None or not zone_m.geom_type.startswith("Polygon"):
                continue
            if zone_m.area <= 1e-6:
                continue
            zidx += 1
            zone_ll = project.to_lonlat(zone_m)
            # valve on the zone boundary closest to the upstream entry
            valve_m = nearest_points(zone_m.boundary, Point(sector["entry_m"]))[0]
            valve_ll = project.to_lonlat(valve_m)

            # major pipe: nearest point on principal -> valve
            proj_t = principal_m.project(Point(valve_m))
            on_princ = principal_m.interpolate(proj_t)
            major_m = LineString([on_princ, valve_m])
            major_ll = project.to_lonlat(major_m)

            # minor pipe: valve -> zone water supply (centroid for part 1)
            target_m = zone_m.centroid
            minor_m = LineString([valve_m, target_m])
            minor_ll = project.to_lonlat(minor_m)

            zone = {
                "idx": zidx,
                "name": "{0}-Z{1:d}".format(sector["name"], zidx),
                "poly_m": zone_m,
                "poly": zone_ll,
                "area_m2": zone_m.area,
                "centroid": project.to_lonlat(target_m),
            }
            zones_all.append(zone)

            valve = {
                "zone": zone["name"],
                "diameter_mm": 50,
                "lon": valve_ll.x,
                "lat": valve_ll.y,
                "point": valve_ll,
                "name": "Valve {0}".format(zone["name"]),
            }
            valves.append(valve)

            majors.append({
                "zone": zone["name"],
                "diameter_mm": 50,
                "line": major_ll,
                "len_m": major_m.length,
            })
            minors.append({
                "zone": zone["name"],
                "diameter_mm": 32,
                "line": minor_ll,
                "len_m": minor_m.length,
            })
            sector.setdefault("zones", []).append(zone)

    cfg["ready"] = True
    cfg["zones"] = zones_all
    cfg["valves"] = valves
    cfg["pipes"] = {
        "principal": {"diameter_mm": 90, "line": principal_ll, "len_m": principal_m.length},
        "majors": majors,
        "minors": minors,
    }
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
        "water": {"lon": pick[0], "lat": pick[1]},
        "basin": basin,
        "basin_m": basin_m,
        "max_elev_m": max_elev_m,
        "configs": configs,
        "existing_sectors": existing_sectors,
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
    return True, None


def extend(plan, cfgid):
    proj = plan["_proj"]
    cfg = [c for c in plan["configs"] if c["id"] == cfgid]
    if not cfg:
        raise ValueError("Unknown config")
    cfg = cfg[0]
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
    for k in ("zones", "valves", "pipes"):
        cfg.pop(k, None)
    extend_config(plan, proj, cfg, plan["_basin_m"], plan.get("max_elev_m"))
    return cfg


def _current_polys(cfg):
    return [(s["poly_m"], s.get("name")) for s in cfg["sectors"]]


def apply_sector_op(plan, cfg, op, idx=None, idx2=None, name=None, ring=None):
    """Apply one sector edit to a config in place. Returns (ok, message).

    Supported ops: rename, remove, merge (idx+idx2), add (ring), edit (idx+ring).
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
        target["name"] = nm
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