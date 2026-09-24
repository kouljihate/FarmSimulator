"""Write the current plan state back out as KML.

Every workflow step (Upload, Basin, Sectors, Zones, Rows, Valves, Pipes,
OtherElements, Trees, Recap) regenerates ``files/<land name>_<Step>.kml``
so the on-disk KML always mirrors what the user has built so far.
"""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES_DIR = os.path.join(BASE, "files")

_XML_ESC = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&apos;",
}


def _esc(s):
    out = str(s if s is not None else "")
    for a, b in _XML_ESC.items():
        out = out.replace(a, b)
    return out


def sanitize_filename(name):
    base = re.sub(r"[^\w\-. ]+", "_", str(name or "land")).strip() or "land"
    return base[:80]


def _ring_coords(poly):
    """Polygon exterior ring as KML lon,lat,0 tuples (lonlat shapely poly)."""
    if poly is None or getattr(poly, "is_empty", True):
        return ""
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    if poly.geom_type != "Polygon":
        return ""
    pts = []
    for x, y in list(poly.exterior.coords):
        pts.append("{0:.7f},{1:.7f},0".format(float(x), float(y)))
    if len(pts) < 3:
        return ""
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return " ".join(pts)


def _line_coords(line):
    if line is None:
        return ""
    if hasattr(line, "geom_type"):
        if line.geom_type == "MultiLineString":
            parts = [_line_coords(g) for g in line.geoms]
            return " | ".join(p for p in parts if p)
        if line.geom_type != "LineString":
            return ""
        coords = list(line.coords)
    else:
        coords = list(line)
    pts = ["{0:.7f},{1:.7f},0".format(float(x), float(y)) for x, y in coords]
    return " ".join(pts) if len(pts) >= 2 else ""


def _polygon_pm(name, coords, style=""):
    if not coords:
        return ""
    su = "\n      <styleUrl>#{0}</styleUrl>".format(style) if style else ""
    return (
        "    <Placemark>\n"
        "      <name>{0}</name>{1}\n"
        "      <Polygon>\n"
        "        <outerBoundaryIs><LinearRing>\n"
        "          <coordinates>{2}</coordinates>\n"
        "        </LinearRing></outerBoundaryIs>\n"
        "      </Polygon>\n"
        "    </Placemark>\n"
    ).format(_esc(name), su, coords)


def _line_pm(name, coords, style=""):
    if not coords:
        return ""
    su = "\n      <styleUrl>#{0}</styleUrl>".format(style) if style else ""
    return (
        "    <Placemark>\n"
        "      <name>{0}</name>{1}\n"
        "      <LineString><coordinates>{2}</coordinates></LineString>\n"
        "    </Placemark>\n"
    ).format(_esc(name), su, coords)


def _point_pm(name, lon, lat, style=""):
    if lon is None or lat is None:
        return ""
    su = "\n      <styleUrl>#{0}</styleUrl>".format(style) if style else ""
    return (
        "    <Placemark>\n"
        "      <name>{0}</name>{1}\n"
        "      <Point><coordinates>{2:.7f},{3:.7f},0</coordinates></Point>\n"
        "    </Placemark>\n"
    ).format(_esc(name), su, float(lon), float(lat))


def _folder(name, body):
    if not body:
        return ""
    return "  <Folder>\n    <name>{0}</name>\n{1}  </Folder>\n".format(
        _esc(name), body)


def plan_to_kml(plan, step="", cfg=None):
    """Serialise plan (+ optional config) to a KML document string."""
    doc_name = plan.get("name") or "land"
    if step:
        doc_name = "{0} - {1}".format(doc_name, step)

    styles = """    <Style id="land">
      <LineStyle><color>ff2f6fa1</color><width>3</width></LineStyle>
      <PolyStyle><color>2e2f6fa1</color></PolyStyle>
    </Style>
    <Style id="extra">
      <LineStyle><color>ff777777</color><width>1</width></LineStyle>
      <PolyStyle><color>22777777</color></PolyStyle>
    </Style>
    <Style id="sector">
      <LineStyle><color>ff8b5cf6</color><width>2</width></LineStyle>
      <PolyStyle><color>228b5cf6</color></PolyStyle>
    </Style>
    <Style id="zone">
      <LineStyle><color>ff22d3ee</color><width>1</width></LineStyle>
      <PolyStyle><color>1a22d3ee</color></PolyStyle>
    </Style>
    <Style id="water">
      <IconStyle><color>ff0000ff</color><scale>1.2</scale></IconStyle>
    </Style>
    <Style id="basin">
      <IconStyle><color>ff8b4513</color><scale>1.2</scale></IconStyle>
    </Style>
    <Style id="valve">
      <IconStyle><color>ff0000ff</color><scale>0.9</scale></IconStyle>
    </Style>
    <Style id="other">
      <IconStyle><color>ff800080</color><scale>1.1</scale></IconStyle>
    </Style>
"""

    # boundaries
    body_b = ""
    for b in plan.get("all_boundaries") or []:
        coords = _ring_coords(b.get("poly"))
        st = "land" if b.get("is_land") else "extra"
        body_b += _polygon_pm(b.get("name") or "Boundary", coords, st)
    if not body_b and plan.get("land") is not None:
        body_b += _polygon_pm(plan.get("name") or "Land",
                              _ring_coords(plan["land"]), "land")

    # water
    body_w = ""
    for w in plan.get("water_points") or []:
        body_w += _point_pm("Water point", w.get("lon"), w.get("lat"), "water")
    if not body_w and plan.get("water"):
        w = plan["water"]
        body_w += _point_pm("Water point", w.get("lon"), w.get("lat"), "water")

    # basins
    body_bs = ""
    for b in plan.get("basins") or []:
        body_bs += _point_pm(b.get("name") or "Basin", b.get("lon"),
                             b.get("lat"), "basin")
    if not body_bs and plan.get("basin"):
        b = plan["basin"]
        body_bs += _point_pm(b.get("name") or "Basin", b.get("lon"),
                             b.get("lat"), "basin")

    # config layers (sectors / zones / valves / pipes / rows)
    body_c = ""
    cfgs = [cfg] if cfg is not None else (plan.get("configs") or [])
    for c in cfgs:
        if not c:
            continue
        cbody = ""
        for s in c.get("sectors") or []:
            cbody += _polygon_pm(s.get("name") or "Sector",
                                 _ring_coords(s.get("poly")), "sector")
            for z in s.get("zones") or []:
                cbody += _polygon_pm(z.get("name") or "Zone",
                                     _ring_coords(z.get("poly")), "zone")
                for line in (z.get("rows") or {}).get("lines") or []:
                    cbody += _line_pm(
                        "Rows {0}".format(z.get("name") or ""),
                        _line_coords(line))
        for v in c.get("valves") or []:
            pt = v.get("point")
            lon = lat = None
            if pt is not None and hasattr(pt, "x"):
                lon, lat = float(pt.x), float(pt.y)
            elif isinstance(pt, dict):
                lon, lat = pt.get("lon"), pt.get("lat")
            elif hasattr(v.get("point"), "get"):
                lon, lat = pt.get("lon"), pt.get("lat")
            if lon is None:
                lon = v.get("lon")
            if lat is None:
                lat = v.get("lat")
            cbody += _point_pm(v.get("name") or v.get("id") or "Valve",
                               lon, lat, "valve")
        pipes = c.get("pipes") or {}
        pr = pipes.get("principal")
        if pr is not None:
            cbody += _line_pm("P90 principal", _line_coords(pr.get("line")))
        for m in pipes.get("majors") or []:
            cbody += _line_pm(
                m.get("name") or "P63 {0}".format(m.get("zone") or ""),
                _line_coords(m.get("line")))
        for m in pipes.get("minors") or []:
            cbody += _line_pm(
                m.get("name") or m.get("pid") or "P32",
                _line_coords(m.get("line")))
        for m in pipes.get("customs") or []:
            cbody += _line_pm(
                m.get("name") or m.get("pid") or "Pipe custom",
                _line_coords(m.get("line")))
        if cbody:
            cname = c.get("name") or "Config {0}".format(c.get("id"))
            if step:
                cname = "{0} ({1})".format(cname, step)
            body_c += _folder(cname, cbody)

    # other elements
    body_o = ""
    for el in plan.get("other_elements") or []:
        label = el.get("kind") or "Element"
        if el.get("size"):
            label = "{0} ({1})".format(label, el.get("size"))
        body_o += _point_pm(label, el.get("lon"), el.get("lat"), "other")

    folders = (
        _folder("Boundaries", body_b)
        + _folder("Water", body_w)
        + _folder("Basins", body_bs)
        + body_c
        + _folder("Other elements", body_o)
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        "    <name>{0}</name>\n"
        "{1}"
        "{2}"
        "  </Document>\n"
        "</kml>\n"
    ).format(_esc(doc_name), styles, folders)


def export_step(plan, step, cfg=None):
    """Write ``files/<name>_<Step>.kml``; return the path (or None on error)."""
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        fname = "{0}_{1}.kml".format(
            sanitize_filename(plan.get("name")), step)
        path = os.path.join(FILES_DIR, fname)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(plan_to_kml(plan, step=step, cfg=cfg))
        return path
    except (OSError, Exception):  # noqa: BLE001 - never fail a workflow step
        return None
