"""Parse user uploads (KML from the Google Maps "My Maps" export, or a CSV)
into lists of land boundary polygons and water points.

Result shape:
    {
      "name": str,
      "polygons": [{"name": str, "description": str, "polygon": Polygon(lon,lat), "vertices_z": [(lon,lat,z), ...]}],
      "water_points": [(lon, lat), ...],
      "source": "kml" | "csv",
    }
"""
import csv
import os
import re
import xml.etree.ElementTree as ET

from shapely.geometry import Polygon
from shapely.validation import make_valid


def _local(tag):
    return tag.rsplit("}", 1)[-1]


_WATER_WORDS = {"water", "point", "source", "puit", "valve", "w"}
_BASIN_WORDS = {"basin", "bassin", "reservoir", "catchment", "pond"}
_LAND_WORDS = {
    "boundary", "boundaries", "land", "parcel", "plot", "field",
    "polygon", "polygone", "ring", "sector", "sectors", "secteur",
    "limite", "parcelle", "terrain", "champ", "foncier",
    "حدود", "أرض", "قطعة",
}


def _words(text):
    return set(re.split(r"\W+", (text or "").lower()))


def _is_water_type(text):
    return bool(_words(text) & _WATER_WORDS)


def _is_land_type(text):
    return bool(_words(text) & _LAND_WORDS)


def _is_basin_type(text):
    return bool(_words(text) & _BASIN_WORDS)


def _coords_from_text(text):
    """'lon,lat[,z] lon,lat[,z] ...' -> [(lon, lat, z)]"""
    out = []
    for part in text.strip().replace("\n", " ").split():
        p = [c for c in part.split(",") if c != ""]
        if len(p) >= 2:
            z = float(p[2]) if len(p) > 2 and p[2] not in ("", "0") else None
            try:
                out.append((float(p[0]), float(p[1]), z))
            except ValueError:
                continue
    return out


def _polygon_from_ring(ring_coords):
    if len(ring_coords) < 4:
        return None
    ring = [(lon, lat) for lon, lat, _ in ring_coords]
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return None
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = make_valid(poly)
        if poly.is_empty:
            return None
    if poly.area <= 0:
        return None
    return poly


def parse_kml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    polygons = []
    water = []
    basins = []

    def handle_placemark(pm, name_hint):
        name = (pm.findtext("{*}name") or name_hint or "Boundary").strip()
        desc_el = pm.find("{*}description")
        desc = "".join(desc_el.itertext()) if desc_el is not None else ""
        full_text = "{0} {1}".format(name, desc)
        for child in pm.iter():
            tag = _local(child.tag)
            if tag == "Polygon":
                ring = _find_ring(child)
                if ring:
                    poly = _polygon_from_ring(ring)
                    if poly is not None:
                        is_basin_poly = _is_basin_type(full_text)
                        if is_basin_poly:
                            polygons.append({"name": name, "description": desc.strip(),
                                             "polygon": poly, "vertices_z": ring})
                            basins.append({
                                "name": name or "Basin",
                                "polygon": poly,
                                "vertices_z": ring,
                                "lon": poly.centroid.x,
                                "lat": poly.centroid.y,
                            })
                        elif _is_water_type(desc):
                            pt = poly.representative_point()
                            water.append((pt.x, pt.y))
                        else:
                            polygons.append({"name": name, "description": desc.strip(),
                                             "polygon": poly, "vertices_z": ring})
            elif tag == "Point":
                if _is_land_type(desc):
                    continue
                coords_el = child.find("{*}coordinates")
                if coords_el is not None:
                    pts = _coords_from_text(coords_el.text or "")
                    if not pts:
                        continue
                    lon, lat = pts[0][0], pts[0][1]
                    if _is_basin_type(full_text):
                        basins.append({"name": name or "Basin", "lon": lon, "lat": lat})
                    else:
                        water.append((lon, lat))
            elif tag == "MultiGeometry":
                pass  # its children are visited by the iter() above

    for pm in root.iter():
        if _local(pm.tag) != "Placemark":
            continue
        handle_placemark(pm, name_hint=None)

    doc_name = None
    for el in root.iter():
        if _local(el.tag) == "Document" and el.findtext("{*}name"):
            doc_name = el.findtext("{*}name")
    basin_points = [
        {"name": b.get("name") or "Basin", "lon": float(b["lon"]), "lat": float(b["lat"])}
        for b in basins
    ]
    return {
        "name": doc_name or os.path.basename(path),
        "polygons": polygons,
        "water_points": water,
        "basins": basins,
        "basin_points": basin_points,
        "source": "kml",
    }


def _find_ring(polygon_el):
    for child in polygon_el.iter():
        if _local(child.tag) == "LinearRing":
            coords_el = child.find("{*}coordinates")
            if coords_el is not None:
                return _coords_from_text(coords_el.text or "")
    return None


_HEADER_KEYS = {
    "lon": ["lon", "lng", "long", "longitude", "x", "e"],
    "lat": ["lat", "latitude", "y", "n"],
    "name": ["name", "label", "title", "id"],
    "type": ["type", "kind", "marker", "category"],
    "z": ["z", "alt", "altitude", "elev", "elevation"],
    "wkt": ["wkt", "geometry", "geom"],
}


def _norm(s):
    return (s or "").strip().lower()


def _match(col, key):
    return _norm(col) in _HEADER_KEYS[key]


def parse_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        raise ValueError("Empty CSV file")

    header = [_norm(c) for c in rows[0]]
    data = rows[1:]
    name = os.path.splitext(os.path.basename(path))[0]
    cols = {k: None for k in _HEADER_KEYS}
    for i, h in enumerate(header):
        for key in _HEADER_KEYS:
            if cols[key] is None and _match(h, key):
                cols[key] = i

    if cols["wkt"] is not None:
        return _parse_wkt_csv(name, cols, data)

    if cols["lon"] is None or cols["lat"] is None:
        raise ValueError(
            "CSV must contain lon/lat columns (lon/lng/longitude/x and lat/latitude/y)"
        )
    rings = []  # list of dicts: name, coords (list of (lon, lat, z))
    water = []
    current = None

    for r in data:
        if not r or all(not c for c in r):
            continue
        def cell(k):
            i = cols[k]
            return r[i].strip() if i is not None and i < len(r) else ""

        typ = cell("type").lower()
        nm = cell("name")
        try:
            lon = float(cell("lon"))
            lat = float(cell("lat"))
        except ValueError:
            continue
        zt = cell("z")
        z = float(zt) if zt not in ("", "0") else None

        if _is_water_type(typ):
            water.append((lon, lat))
            continue

        if not typ and cols["type"] is None:
            if current is None:
                current = {"name": nm or "Boundary", "coords": []}
                rings.append(current)
            current["coords"].append((lon, lat, z))
            continue

        if "bound" in typ or "polygon" in typ or "ring" in typ or "new" in typ:
            current = {"name": nm or "Boundary {0:d}".format(len(rings) + 1), "coords": []}
            rings.append(current)
        elif current is not None:
            current["coords"].append((lon, lat, z))

    polygons = []
    for ring in rings:
        poly = _polygon_from_ring(ring["coords"])
        if poly is not None:
            polygons.append({"name": ring["name"], "description": "",
                             "polygon": poly, "vertices_z": ring["coords"]})

    return {
        "name": name,
        "polygons": polygons,
        "water_points": water,
        "source": "csv",
    }


def _parse_wkt_csv(name, cols, data):
    polygons, water = [], []
    for r in data:
        # an unquoted WKT containing commas gets split across cells by csv.reader;
        # rejoin the remaining cells of the row back into one WKT string.
        parts = [c.strip() for c in r[cols["wkt"]:] if c.strip()]
        w = ", ".join(parts) if parts else ""
        if not w:
            continue
        up = w.upper()
        if up.startswith("POINT"):
            lon, lat = _point_from_wkt(w)
            if lon is not None:
                water.append((lon, lat))
        else:
            poly = _polygon_from_wkt(w)
            if poly is not None:
                dx = cols["name"]
                nm = r[dx].strip() if dx is not None and dx < len(r) else "Boundary"
                polygons.append({"name": nm, "description": "",
                                 "polygon": poly, "vertices_z": []})
    return {"name": name, "polygons": polygons, "water_points": water, "source": "csv"}


def _point_from_wkt(w):
    import re

    m = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", w)
    if len(m) >= 2:
        return float(m[0]), float(m[1])
    return None, None


def _polygon_from_wkt(w):
    from shapely import wkt as shp_wkt

    try:
        geom = shp_wkt.loads(w)
    except Exception:
        return None
    if geom.geom_type == "Polygon":
        return geom if geom.is_valid and geom.area > 0 else None
    if geom.geom_type == "MultiPolygon":
        parts = [g for g in geom.geoms if g.area > 0]
        return _merge_multi(parts) if parts else None
    return None


def _merge_multi(parts):
    from shapely.ops import unary_union

    u = unary_union(parts)
    return u


def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".kml":
        return parse_kml(path)
    if ext in (".csv", ".txt"):
        return parse_csv(path)
    raise ValueError("Unsupported file type (use .kml or .csv)")