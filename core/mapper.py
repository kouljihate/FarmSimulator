"""Turn planning results into standalone folium/leaflet maps (HTML strings)."""
import folium

from . import i18n

DN = "OpenStreetMap"


def _lnglat(point):
    # shapely point already (x=lon, y=lat)
    return [point.x, point.y]


def _poly_locations(geom):
    """Returns a list of rings [[lat, lng], ...] for a (Multi)Polygon."""
    rings = []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for p in polys:
        rings.append([[y, x] for x, y in list(p.exterior.coords)])
    return rings


def _line_locations(geom):
    if geom.geom_type == "MultiLineString":
        return [[[y, x] for x, y in ls.coords] for ls in geom.geoms]
    return [[[y, x] for x, y in geom.coords]]


class Layers:
    """Fluent builder for the items drawn on one map."""

    def __init__(self):
        self.items = []

    def boundary(self, geom, name="Boundary", color="#222222", weight=2, fill=None, fill_opacity=0.0):
        self.items.append({
            "kind": "polygon", "geom": geom, "name": name, "color": color,
            "weight": weight, "fill": fill, "fill_opacity": fill_opacity, "dash": None,
        })
        return self

    def dashed(self, geom, name, color, weight=3):
        self.items.append({
            "kind": "polygon", "geom": geom, "name": name, "color": color,
            "weight": weight, "fill": None, "fill_opacity": 0.0, "dash": "4, 4",
        })
        return self

    def polygon(self, geom, name, color, fill_opacity, weight=1):
        self.items.append({
            "kind": "polygon", "geom": geom, "name": name, "color": color,
            "weight": weight, "fill": color, "fill_opacity": fill_opacity, "dash": None,
        })
        return self

    def line(self, geom, name, color, weight=3, dash=None):
        self.items.append({
            "kind": "line", "geom": geom, "name": name, "color": color,
            "weight": weight, "dash": dash,
        })
        return self

    def marker(self, lon, lat, name, color, icon="circle", radius=None):
        self.items.append({
            "kind": "marker", "lon": lon, "lat": lat, "name": name,
            "color": color, "icon": icon, "radius": radius,
        })
        return self


def _render_base(center, zoom):
    return folium.Map(location=center, zoom_start=zoom, control_scale=True,
                      tiles=DN, prefer_canvas=True)


def build(layers, center, zoom=16):
    m = _render_base(center, zoom)
    for it in layers.items:
        name = it.get("name", "")
        if it["kind"] == "polygon":
            color = it["color"]
            fill = it.get("fill") or color
            folium.Polygon(
                _poly_locations(it["geom"]),
                color=color,
                weight=it["weight"],
                opacity=0.9,
                fill=True,
                fill_color=fill,
                fill_opacity=it.get("fill_opacity", 0.0),
                dash_array=it.get("dash"),
                tooltip=name,
            ).add_to(m)
        elif it["kind"] == "line":
            for loc in _line_locations(it["geom"]):
                if len(loc) < 2:
                    continue
                folium.PolyLine(
                    loc,
                    color=it["color"],
                    weight=it["weight"],
                    opacity=0.95,
                    dash_array=it.get("dash"),
                    tooltip=name,
                ).add_to(m)
        elif it["kind"] == "marker":
            _add_marker(m, it)
    return m


def _add_marker(m, it):
    loc = [it["lat"], it["lon"]]
    color = it["color"]
    radius = it.get("radius", 9)
    if it.get("icon") == "circle":
        folium.CircleMarker(
            loc, radius=radius, color=color, weight=2,
            fill=True, fill_opacity=0.85, tooltip=it["name"],
            popup=it["name"],
        ).add_to(m)
    else:
        folium.CircleMarker(
            loc, radius=radius, color=color, weight=3, fill=True,
            fill_opacity=1.0, tooltip=it["name"], popup=it["name"],
        ).add_to(m)


def to_html(m, height="100%"):
    m.get_root().render()
    return m.get_root()._repr_html_()


# --------------------------------------------------------------------------- #
# Application-specific map recipes
# --------------------------------------------------------------------------- #
def _ti(key, **kw):
    return i18n.map_tip(key, **kw)


def _bn(name):
    # bilingual-neutral for arbitrary user names
    return i18n.bl_style(name, name)


def _marker(plan, lay, key, lon, lat, color, radius, **kw):
    lay.marker(lon, lat, _ti(key, **kw), color, radius=radius)


def _drag_js():
    """Script for the basin map.

    Exposes `window.basinSet(lon, lat)` so the parent page can move the marker,
    and posts `{type:'basin-marker-drag', lon, lat}` to the top window when the
    user drags it (the map lives one extra folium iframe deep, so *top*, not
    parent).
    """
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;var mk=null;"
        "mp.eachLayer(function(l){if(!mk&&l&&l.getLatLng&&l.options&&l.options.draggable){mk=l;}});"
        "if(!mk)return;"
        "window.basinSet=function(lon,lat){try{mk.setLatLng([lat,lon]);}catch(x){}};"
        "mk.on('dragend',function(e){var p=e.target.getLatLng();"
        "try{window.top.postMessage({type:'basin-marker-drag',lon:p.lng,lat:p.lat},'*');}catch(x){}});"
        "});"
    ) + "</script>"


def map_basin(plan):
    lay = Layers()
    for b in plan["all_boundaries"]:
        if b["is_land"]:
            lay.boundary(b["poly"], _bn(b["name"]), color="#333333",
                         fill="#1f77b4", fill_opacity=0.12, weight=2)
        else:
            lay.dashed(b["poly"], _bn(b["name"]), color="#777777", weight=1)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 11)
    me = plan["basin"].get("max_elev")
    if me:
        _marker(plan, lay, "maxelev", me["lon"], me["lat"], "green", 9, z=me["z"])
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    m = build(lay, center, 16)
    tip = _ti("basin_rec")
    folium.Marker(
        [plan["basin"]["lat"], plan["basin"]["lon"]],
        draggable=True,
        icon=folium.Icon(color="darkred"),
        popup=tip,
        tooltip=tip,
    ).add_to(m)
    m.get_root().html.add_child(folium.Element(_drag_js()))
    return to_html(m)


_ZONE_COLORS = ["#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]


def map_config_preview(plan, cfg):
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)
    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                    colors[s["idx"]], 0.14, weight=2)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 8)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 10)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    return to_html(build(lay, center, 16))


def map_config_overview(plan, cfg):
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)

    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                    colors[s["idx"]], 0.10, weight=2)

    pr = cfg["pipes"]["principal"]
    lay.line(pr["line"], _ti("principal"), "#0b8a6f", 5)
    for maj in cfg["pipes"]["majors"]:
        lay.line(maj["line"], _ti("major", zone=maj["zone"]), "#377eb8", 3)
    for mn in cfg["pipes"]["minors"]:
        lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    for v in cfg["valves"]:
        lay.marker(v["lon"], v["lat"], _ti("valve", zone=v["zone"]), "red", radius=6)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 9)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    return to_html(build(lay, center, 16))


def _sector_color_map(cfg):
    # generous palette so sectors stay identifiable
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    return {s["idx"]: palette[(s["idx"] - 1) % len(palette)] for s in cfg["sectors"]}


def map_sector(plan, cfg, sector):
    lay = Layers()
    zonemap = {z["idx"]: z for z in sector.get("zones", [])}
    for i in range(1, len(zonemap) + 1):
        z = zonemap[i]
        lay.polygon(z["poly"], _ti("zone", name=z["name"], area=z["area_m2"]),
                    _ZONE_COLORS[(i - 1) % len(_ZONE_COLORS)], 0.18, weight=2)

    pr = cfg["pipes"]["principal"]
    lay.line(pr["line"], _ti("principal"), "#0b8a6f", 4)
    for maj in cfg["pipes"]["majors"]:
        if maj["zone"].startswith(sector["name"] + "-"):
            lay.line(maj["line"], _ti("major", zone=maj["zone"]), "#377eb8", 3)
    for mn in cfg["pipes"]["minors"]:
        if mn["zone"].startswith(sector["name"] + "-"):
            lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    for v in cfg["valves"]:
        if v["zone"].startswith(sector["name"] + "-"):
            lay.marker(v["lon"], v["lat"], _ti("valve", zone=v["zone"]), "red", radius=7)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 8)
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 1)
    nm = sector["centroid"]
    lay.marker(nm.x, nm.y, _ti("sector", name=sector["name"], area=sector["area_m2"]),
               "#111111", radius=3)
    center = [sector["centroid"].y, sector["centroid"].x]
    return to_html(build(lay, center, 18))