"""Projection and affine helpers.

All geometric work happens in a local projected frame (metres, UTM) so that
areas, distances and splitting behave like Euclidean land measurements.
"""
import math

from pyproj import Transformer
from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from shapely.ops import transform as shp_transform


def utm_epsg(lon, lat):
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))
    if lat >= 0:
        return "EPSG:{:d}".format(32600 + zone)
    return "EPSG:{:d}".format(32700 + zone)


class Projector:
    """Bidirectional lon/lat <-> local metres transformer."""

    def __init__(self, lon, lat):
        self.lon = float(lon)
        self.lat = float(lat)
        self.epsg = utm_epsg(self.lon, self.lat)
        self._fwd = Transformer.from_crs("EPSG:4326", self.epsg, always_xy=True)
        self._inv = Transformer.from_crs(self.epsg, "EPSG:4326", always_xy=True)

    def to_m(self, geom):
        return shp_transform(lambda x, y: self._fwd.transform(x, y), geom)

    def to_lonlat(self, geom):
        return shp_transform(lambda x, y: self._inv.transform(x, y), geom)


def _affine_params(angle_deg, origin):
    """Affine transform mapping world points into a rotated frame.

    `origin` is in the same frame as the input geometry. Frame axis 1 (x') is
    the sweep/scan direction, axis 2 (y') is that direction rotated +90 deg.

    Matrices follow the shapely.affinity.affine_transform convention:
        x' = a*x + b*y + xoff,   y' = d*x + e*y + yoff
    i.e. m = [a, b, d, e, xoff, yoff].
    """
    a = math.radians(angle_deg)
    ex, ey = math.cos(a), math.sin(a)
    sx, sy = -ey, ex
    ox, oy = origin.x, origin.y
    fwd = [ex, ey, sx, sy, -(ox * ex + oy * ey), -(ox * sx + oy * sy)]
    return fwd, _invert(fwd)


def _invert(m):
    a, b, d, e, offx, offy = m
    det = a * e - b * d
    ia, ib = e / det, -b / det
    id_, ie = -d / det, a / det
    nx = -(ia * offx + ib * offy)
    ny = -(id_ * offx + ie * offy)
    return [ia, ib, id_, ie, nx, ny]


_BIG = 1e7


def _cap_area(fp, xmin, x):
    box = Polygon([(xmin - 1e-6, -_BIG), (x, -_BIG), (x, _BIG), (xmin - 1e-6, _BIG)])
    return fp.intersection(box).area


def sweep_split(poly, angle_deg, n_parts):
    """Split *poly* (a projected 2D polygon) into n equal-area pieces.

    Pieces are cut with scan-lines running along *angle_deg*; the pieces are
    returned ordered along the perpendicular sweep direction.

    When the piece order does not matter (n_parts == 1) the original polygon
    is returned unchanged.
    """
    if poly is None or poly.is_empty or not poly.geom_type.startswith("Polygon"):
        return [poly]
    if n_parts <= 1:
        return [poly]

    origin = poly.centroid
    fwd, inv = _affine_params(angle_deg, origin)
    fp = affine_transform(poly, fwd)
    xmin, _, xmax, _ = fp.bounds
    total = fp.area
    if total <= 0:
        return [poly]

    cuts = []
    for k in range(1, n_parts):
        target = total * k / n_parts
        lo, hi = xmin, xmax
        for _ in range(70):
            mid = (lo + hi) / 2.0
            if _cap_area(fp, xmin, mid) < target:
                lo = mid
            else:
                hi = mid
        cuts.append((lo + hi) / 2.0)

    xs = [xmin] + cuts + [xmax]
    pieces = []
    for i in range(n_parts):
        cl, cr = xs[i], xs[i + 1]
        box = Polygon([(cl - 1e-6, -_BIG), (cr, -_BIG), (cr, _BIG), (cl - 1e-6, _BIG)])
        piece = fp.intersection(box)
        if piece.geom_type != "Polygon" and piece.geom_type != "MultiPolygon":
            subs = list(piece.geoms) if hasattr(piece, "geoms") else [piece]
            polys = [g for g in subs if g.geom_type == "Polygon" and g.area > 0]
            piece = max(polys, key=lambda g: g.area) if polys else None
        if piece is not None and piece.area > 1e-6:
            pieces.append(affine_transform(piece, inv))
    return pieces


def main_axis_angle(poly):
    """Angle (deg) of the major axis of the polygon's minimum rotated rectangle."""
    mrr = poly.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    best, best_a = 0.0, 0.0
    n = len(coords)
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        d = math.hypot(x2 - x1, y2 - y1)
        if d > best:
            best = d
            best_a = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return best_a