"""Compact, deterministic sectorisation by recursive area-balanced splitting.

The land (possibly concave, possibly with holes, possibly MultiPolygon) is
partitioned with a "land-and-water kd-tree":

  * start from the whole land as a single cell;
  * repeatedly take the cell with the largest area (or the most elongated one)
    and split it with a straight cut that places a controlled *fraction* of the
    cell's area on each side;
  * the cut runs along the cell's longest local axis, so the two children stay
    close to square (no long thin strips / slivers);
  * every cut is a plain polygon/box intersection (see `_split_once`), the same
    affine-transform + box-clipping trick used by `geo.sweep_split`, so concave
    land and holes are preserved automatically.

Tiny slivers produced by cuts across concave notches are folded back into their
nearest neighbour (`_clean_slivers`) so they never survive as real sectors.
Everything is deterministic: same input polygon + parameters -> same output.

Varying the target cell area, the global orientation of the split axes, the
split-area fraction and the "who to split next" heuristic produces several
visibly different alternative configs from one parcel.
"""
from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from .geo import _affine_params, main_axis_angle

_BIG = 1e7
_MIN_PIECE_FRAC = 0.004  # pieces below 0.4% of the parent area are folded away
_MAX_CELLS = 250
_MAX_SPLITS = 4096


def _parts(geom):
    """Flatten a geometry into its Polygon parts (tolerating collections)."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return _parts_all(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        return _parts_all(geom.geoms)
    return []


def _parts_all(geoms):
    out = []
    for g in geoms:
        out.extend(_parts(g))
    return out


def _repair(geom):
    """Repair an invalid polygon (rare numeric artefacts from long cuts)."""
    return make_valid(geom) if not geom.is_valid else geom


def _box(x0, x1):
    return Polygon([(x0, -_BIG), (x1, -_BIG), (x1, _BIG), (x0, _BIG)])


def _frame(cell, angle_deg):
    """Affine-transform *cell* into a frame centred on its centroid.

    Returns (fp, inv, w1, w2) where fp is the transformed polygon, inv the
    inverse affine params, and w1/w2 are the x'/y' extents of fp (i.e. the
    cell sizes along *angle_deg* and *angle_deg + 90*).
    """
    origin = cell.centroid
    fwd, inv = _affine_params(angle_deg, origin)
    fp = affine_transform(cell, fwd)
    minx, miny, maxx, maxy = fp.bounds
    return fp, inv, (maxx - minx), (maxy - miny)


def _area_left(fp, cut_x):
    xmin = fp.bounds[0]
    return fp.intersection(_box(xmin - 1e-6, cut_x)).area


def _find_cut(fp, target_area):
    """x' where the area of fp left of x' equals *target_area* (binary search)."""
    xmin, _, xmax, _ = fp.bounds
    lo, hi = xmin, xmax
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _area_left(fp, mid) < target_area:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _split_once(cell, scan_angle, fraction):
    """Cut *cell* with lines running along *scan_angle*; return child polygons.

    One side of the cut holds `fraction * area` of the cell. Children may be
    MultiPolygons (concave land) and are returned as their individual parts.
    """
    fp, inv, _, _ = _frame(cell, scan_angle)
    cut = _find_cut(fp, fp.area * fraction)
    xmin, _, xmax, _ = fp.bounds
    left = affine_transform(_repair(fp.intersection(_box(xmin - 1e-6, cut))), inv)
    right = affine_transform(_repair(fp.intersection(_box(cut, xmax + 1e-6))), inv)
    return _parts(left) + _parts(right)


def _clean_slivers(parent, children):
    """Drop tiny slivers: fold any piece < 0.4% of the parent area into its
    nearest sibling so the union of the children still covers the parent."""
    thresh = _MIN_PIECE_FRAC * parent.area
    big = [c for c in children if c.area >= thresh]
    tiny = [c for c in children if c.area < thresh]
    if not tiny or not big:
        pieces = big if big else children
    else:
        for t in tiny:
            tc = t.centroid
            nearest = min(big, key=lambda b: b.centroid.distance(tc))
            i = big.index(nearest)
            merged = nearest.union(t)
            if merged.geom_type == 'MultiPolygon':
                big[i] = max(merged.geoms, key=lambda g: g.area)
            else:
                big[i] = merged
        pieces = big
    out = []
    for p in pieces:
        out.extend(_parts(_repair(p)))
    return out


def _elongation(cell, angle_deg):
    _, _, w1, w2 = _frame(cell, angle_deg)
    short = min(w1, w2)
    return max(w1, w2) / short if short > 1e-9 else float("inf")


def partition(land_m, target_area, axis_angle, fraction=0.5, pick="largest"):
    """Partition *land_m* into cells of area <= target_area.

    Returns a list of (poly_m, zone_angle_deg) where poly_m is one cell and
    zone_angle_deg is the angle of the cut lines to use for that cell's zones
    (i.e. perpendicular to the cell's own major axis).

    Parameters
    ----------
    target_area : float
        maximum area per cell (e.g. 10 000 m2).
    axis_angle : float
        global orientation (deg) of the preferred splitting frame.
    fraction : float, 0 < fraction < 1
        area fraction placed on one side of every cut; 0.5 = balanced,
        larger/smaller values produce mixed cell sizes (mosaic look).
    pick : "largest" | "elongated"
        which cell is split next: the largest one or the most elongated one.
    """
    cells = _parts(land_m) if _parts(land_m) else [land_m]
    if not cells:
        return []

    guard = 0
    while True:
        todo = [c for c in cells if c.area > target_area + 1e-6]
        if not todo or len(cells) >= _MAX_CELLS or guard >= _MAX_SPLITS:
            break
        guard += 1
        if pick == "elongated":
            cell = max(todo, key=lambda c: _elongation(c, axis_angle))
        else:
            cell = max(todo, key=lambda c: c.area)
        cells.remove(cell)

        _, _, w1, w2 = _frame(cell, axis_angle)
        # cut the cell across its LONGER local axis: if it is longer along
        # axis_angle+90 (w2) the cut lines run along axis_angle and vice versa.
        scan_angle = axis_angle if w2 >= w1 else axis_angle + 90.0
        children = _clean_slivers(cell, _split_once(cell, scan_angle, fraction))
        cells.extend(children)

    out = []
    for c in cells:
        for part in _parts(_repair(c)):
            if part.area > 1e-6:
                out.append((part, main_axis_angle(part) + 90.0))

    # remove cells whose centroid falls inside another cell (overlaps)
    cleaned = []
    for poly, angle in out:
        contained = False
        for other_poly, _ in out:
            if poly is not other_poly and other_poly.contains(poly.centroid):
                contained = True
                break
        if not contained:
            cleaned.append((poly, angle))
    return cleaned