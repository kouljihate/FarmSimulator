"""Turn planning results into standalone folium/leaflet maps (HTML strings)."""
import folium
import html as _html

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


def _sector_select_js(cfg):
    """Script for the sectorisation preview maps.

    Renders each sector polygon with an extra `sector` option (folium drops
    unknown options, so they are added directly via Leaflet) and supports
    multi-selection: `window.selectSectors([...])` sets the checked set from
    the parent checkboxes, `window.toggleSector(idx)` flips one, and a single
    `window.selectSector(idx)` is kept for legacy/load_run checks. Clicking a
    sector in the map toggles it and posts
    `{type:'sector-select', cfg, idx, checked}` to the top window (the map
    lives one extra folium iframe deep, so *top*, not parent).
    """
    import json
    sectors = []
    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        sectors.append({
            "idx": s["idx"],
            "color": colors[s["idx"]],
            "locs": _poly_locations(s["poly"]),
            "tip": _ti("sector", name=s["name"], area=s["area_m2"]),
        })
    data = json.dumps(sectors)
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;"
        "var SECTORS=" + data + ";"
        "var defs={},order=[],checked={};"
        "function pushSector(o,pl){"
        "if(!defs[o.idx]){defs[o.idx]=[];order.push(o.idx);}"
        "defs[o.idx].push({l:pl,o:{color:o.color,weight:2,fillColor:o.color,fillOpacity:.14}});"
        "pl.on('click',function(ev){window.toggleSector(ev.target.options.sector);"
        "try{window.top.postMessage({type:'sector-select',cfg:" + str(cfg["id"]) + ",idx:ev.target.options.sector,checked:!!checked[ev.target.options.sector]},'*');}catch(x){}});"
        "}"
        "for(var i=0;i<SECTORS.length;i++){var o=SECTORS[i];"
        "var pl=L.polygon(o.locs,{color:o.color,weight:2,opacity:.9,"
        "fill:true,fillColor:o.color,fillOpacity:.14,sector:o.idx});"
        "pl.addTo(mp);pl.bindTooltip(o.tip,{sticky:true});pl.bringToBack();"
        "pushSector(o,pl);}"
        "function applySel(){for(var a=0;a<order.length;a++){var on=!!checked[order[a]];"
        "var z=defs[order[a]];for(var b=0;b<z.length;b++){var q=z[b];"
        "q.l.setStyle(on?{color:'#000000',weight:4,fillColor:'#ffd700',fillOpacity:.5}:q.o);"
        "if(on)q.l.bringToFront();}}}"
        "window.selectSectors=function(list){checked={};"
        "for(var i=0;i<list.length;i++)checked[list[i]]=true;applySel();};"
        "window.toggleSector=function(idx){checked[idx]=!checked[idx];applySel();};"
        "window.selectSector=function(idx){checked={};checked[idx]=true;applySel();};"
        "});"
    ) + "</script>"


def _sector_manage_js(cfg):
    """Script that powers sector drawing and boundary editing on the preview
    maps.

    Exposes `startDraw/cancelDraw/finishDraw` (click to build a new sector
    polygon, finish posts `{type:'sector-draw', cfg, ring}`) and
    `startEdit(idx, ring)/cancelEdit/finishEdit` (draggable vertex handles,
    finish posts `{type:'sector-edit', cfg, idx, ring}`). Escape cancels either
    mode (posts `{type:'sector-cancel', cfg}`). Messages go to `window.top`
    (the map lives one extra folium iframe deep).
    """
    cfgid = cfg["id"]
    js = (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;var CFG=" + str(cfgid) + ";"
        "var drawMode=false,editMode=false,editIdx=null,verts=[],layers=[];"
        "function rmAll(){for(var i=0;i<layers.length;i++){try{if(layers[i])mp.removeLayer(layers[i]);}catch(x){}}"
        "if(layers['poly'])try{mp.removeLayer(layers['poly']);}catch(x){}layers=[];}"
        "function post(type,extra){var o={type:type,cfg:CFG};for(var k in extra)o[k]=extra[k];"
        "try{window.top.postMessage(o,'*');}catch(x){}}"
        "function ring(){var rr=[];for(var i=0;i<verts.length;i++)rr.push([verts[i].lng,verts[i].lat]);"
        "if(verts.length>1)rr.push(rr[0]);return rr;}"
        "function drawPoly(){var loc=[];for(var i=0;i<verts.length;i++)loc.push([verts[i].lat,verts[i].lng]);"
        "if(layers['poly'])try{mp.removeLayer(layers['poly']);}catch(x){}"
        "layers['poly']=loc.length>2?L.polygon(loc,{color:'#ffd700',weight:2,fillColor:'#ffd700',fillOpacity:.25}):null;"
        "if(layers['poly'])layers['poly'].addTo(mp);}"
        "function onDrawClick(e){"
        "var m=L.circleMarker(e.latlng,{radius:5,color:'#ffd700',weight:2,fill:true,fillColor:'#fff',fillOpacity:1});"
        "m.addTo(mp);layers.push(m);verts.push(e.latlng);drawPoly();}"
        "window.startDraw=function(){if(drawMode)return;drawMode=true;verts=[];rmAll();"
        "mp.on('click',onDrawClick);post('sector-draw-start',{});};"
        "window.finishDraw=function(){if(!drawMode)return;mp.off('click',onDrawClick);drawMode=false;"
        "var r=ring();rmAll();verts=[];if(r.length>=4)post('sector-draw',{ring:r});};"
        "window.cancelDraw=function(){if(!drawMode)return;mp.off('click',onDrawClick);drawMode=false;rmAll();verts=[];"
        "post('sector-cancel',{});};"
        "window.startEdit=function(idx,ring){if(drawMode)window.cancelDraw();if(editMode)return;editMode=true;editIdx=idx;"
        "rmAll();verts=[];var loc=[];"
        "for(var i=0;i<ring.length;i++){"
        "if(!ring[i]||ring[i].length<2)continue;"
        "var ll=L.latLng(ring[i][1],ring[i][0]);"
        "if(verts.length&&ll.equals(verts[verts.length-1]))continue;"
        "loc.push([ll.lat,ll.lng]);verts.push(ll);"
        "var m=L.marker(ll,{draggable:true});m.addTo(mp);layers.push(m);"
        "m.on('drag',function(){vertMoved();});}"
        "layers['poly']=L.polygon(loc,{color:'#ffd700',weight:3,fillColor:'#22d3ee',fillOpacity:.18}).addTo(mp);"
        "post('sector-edit-start',{idx:idx});};"
        "function vertMoved(){var loc=[];for(var i=0;i<verts.length;i++)loc.push([verts[i].lat,verts[i].lng]);"
        "if(layers['poly'])layers['poly'].setLatLngs(loc);}"
        "window.finishEdit=function(){if(!editMode)return;editMode=false;var r=ring();var was=editIdx;"
        "rmAll();verts=[];editIdx=null;if(r.length>=4)post('sector-edit',{idx:was,ring:r});};"
        "window.cancelEdit=function(){if(!editMode)return;editMode=false;rmAll();verts=[];editIdx=null;"
        "post('sector-cancel',{});};"
        "window.addEventListener('keydown',function(e){"
        "if(e.key==='Escape'){if(drawMode)window.cancelDraw();else if(editMode)window.cancelEdit();}});"
        "});"
    )
    return "<script>" + js + "</script>"


def map_config_preview(plan, cfg):
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 8)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 10)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    m = build(lay, center, 16)
    m.get_root().html.add_child(folium.Element(_sector_select_js(cfg)))
    m.get_root().html.add_child(folium.Element(_sector_manage_js(cfg)))
    return to_html(m)


def map_config_overview(plan, cfg):
    """Full map for the Final Result tab: land, zones, valves and all piping."""
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)

    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                    colors[s["idx"]], 0.10, weight=2)
    for z in cfg.get("zones", []):
        lay.polygon(z["poly"], _ti("zone", name=z["name"], area=z["area_m2"]),
                    "#ff7f0e", 0.08, weight=1)

    pr = cfg["pipes"]["principal"]
    lay.line(pr["line"], _ti("principal"), "#0b8a6f", 5)
    for maj in cfg["pipes"]["majors"]:
        lay.line(maj["line"], _ti("major63", zone=maj["zone"]), "#377eb8", 3)
    for mn in cfg["pipes"]["minors"]:
        lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    for v in cfg["valves"]:
        if v.get("kind") == "principal":
            lay.marker(v["lon"], v["lat"], _ti("valve90", zone=v.get("sector") or v["zone"]), "red", radius=9)
        else:
            lay.marker(v["lon"], v["lat"], _ti("valve32", zone=v["zone"]), "orange", radius=6)
    for el in plan.get("other_elements") or []:
        lay.marker(el["lon"], el["lat"], _bn(str(el.get("kind"))), "purple", radius=7)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 9)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    return to_html(build(lay, center, 16))


def map_config_valves(plan, cfg, only_zone=None):
    """Valve step map: sectors + zones + draggable valves (no piping).

    With `only_zone` set, only that zone (emphasized) and its secondary
    valves are drawn, centred and zoomed on the zone.
    """
    zones = [z for z in cfg.get("zones", [])
             if only_zone is None or z.get("name") == only_zone]
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)
    if only_zone is None:
        colors = _sector_color_map(cfg)
        for s in cfg["sectors"]:
            lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                        colors[s["idx"]], 0.10, weight=2)
    for z in zones:
        lay.polygon(z["poly"], _ti("zone", name=z["name"], area=z["area_m2"]),
                    "#ff7f0e", 0.18 if only_zone else 0.08,
                    weight=3 if only_zone else 1)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 9)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    if only_zone and zones and zones[0].get("centroid") is not None:
        c0 = zones[0]["centroid"]
        center, zoom = [c0.y, c0.x], 18
    else:
        center, zoom = [plan["basin"]["lat"], plan["basin"]["lon"]], 16
    m = build(lay, center, zoom)
    for z in zones:
        c = z.get("centroid")
        if c is None:
            continue
        folium.map.Marker(
            [c.y, c.x],
            icon=folium.DivIcon(html=_zone_label(z["name"])),
        ).add_to(m)
    m.get_root().html.add_child(folium.Element(_valve_manage_js(cfg, only_zone)))
    return to_html(m)


def map_config_pipes(plan, cfg):
    """Pipes step map: sectors + piping 90/63/32 mm (no valves)."""
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)
    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                    colors[s["idx"]], 0.10, weight=2)
    pr = cfg["pipes"]["principal"]
    lay.line(pr["line"], _ti("principal"), "#0b8a6f", 5)
    for maj in cfg["pipes"]["majors"]:
        lay.line(maj["line"], _ti("major63", zone=maj["zone"]), "#377eb8", 3)
    for mn in cfg["pipes"]["minors"]:
        lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 9)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    return to_html(build(lay, center, 16))


def map_other_elements(plan, cfg):
    """Big land map for the Other Elements tab: network + placed elements."""
    lay = Layers()
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 2)
    colors = _sector_color_map(cfg)
    for s in cfg["sectors"]:
        lay.polygon(s["poly"], _ti("sector", name=s["name"], area=s["area_m2"]),
                    colors[s["idx"]], 0.08, weight=2)
    try:
        pr = cfg["pipes"]["principal"]
        lay.line(pr["line"], _ti("principal"), "#0b8a6f", 4)
        for maj in cfg["pipes"].get("majors", []):
            lay.line(maj["line"], _ti("major63", zone=maj["zone"]), "#377eb8", 3)
        for mn in cfg["pipes"].get("minors", []):
            lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    except (KeyError, TypeError):
        pass
    for el in plan.get("other_elements") or []:
        lay.marker(el["lon"], el["lat"], _bn("{0} ({1})".format(el.get("kind"), el.get("size") or "")),
                   "purple", radius=8)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 9)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    center = [plan["basin"]["lat"], plan["basin"]["lon"]]
    m = build(lay, center, 16)
    m.get_root().html.add_child(folium.Element(_other_pick_js()))
    return to_html(m)


def _valve_manage_js(cfg, only_zone=None):
    """Script for the Valve step map.

    Draws every valve as a draggable Leaflet marker (principal = big red,
    secondary = orange). Clicking a marker posts
    ``{type:'valve-select', cfg, valve: {...}}`` to the top window and opens a
    popup with the full valve info; releasing a drag posts
    ``{type:'valve-drag', cfg, valve_id, lon, lat}`` so the parent can update
    the info live and persist the move. Clicks on empty map still post
    ``{type:'valve-map-click', lon, lat}``. With `only_zone`, only that zone's
    secondary valves get markers.
    """
    import json
    valves = []
    for v in cfg.get("valves") or []:
        if only_zone is not None and (v.get("kind") == "principal"
                                      or v.get("zone") != only_zone):
            continue
        valves.append({
            "id": v.get("id"),
            "name": v.get("name"),
            "kind": v.get("kind"),
            "sector": v.get("sector"),
            "zone": v.get("zone"),
            "diameter_mm": v.get("diameter_mm", 90 if v.get("kind") == "principal" else 32),
            "lon": v.get("lon"),
            "lat": v.get("lat"),
        })
    data = json.dumps(valves)
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp||!window.L)return;"
        "var CFG=" + str(cfg["id"]) + ";"
        "var VALVES=" + data + ";"
        "function dot(v){return '<div class=\"valve-marker\" style=\"width:'"
        "+(v.kind==='principal'?18:14)+'px;height:'+(v.kind==='principal'?18:14)+'px;'"
        "+'border-radius:50%;background:'+(v.kind==='principal'?'red':'orange')+';'"
        "+'border:3px solid #fff;box-shadow:0 0 10px '+(v.kind==='principal'?'red':'orange')+';'"
        "+'cursor:grab;\"></div>';}"
        "function infoHtml(v){return '<div style=\"font-family:Comfortaa,sans-serif;font-size:12px;color:#0b1220;line-height:1.5;min-width:170px;\">'"
        "+'<b>'+String(v.name).replace(/[<>&]/g,'')+'</b><br>'"
        "+'<span>'+v.kind+' - '+v.diameter_mm+' mm</span><br>'"
        "+'<span>Sector: '+String(v.sector).replace(/[<>&]/g,'')+' | Zone: '+String(v.zone).replace(/[<>&]/g,'')+'</span><br>'"
        "+'<span>X '+Number(v.lon).toFixed(6)+' / Y '+Number(v.lat).toFixed(6)+'</span></div>';}"
        "function post(o){try{window.top.postMessage(o,'*');}catch(x){}}"
        "var marks={};"
        "VALVES.forEach(function(v){"
        "var mk=L.marker([v.lat,v.lon],{draggable:true,"
        "icon:L.divIcon({className:'',html:dot(v),iconSize:null})});"
        "mk.addTo(mp);mk.bindTooltip(v.name,{sticky:true});mk.bindPopup(infoHtml(v));"
        "marks[v.id]=mk;"
        "mk.on('click',function(e){"
        "try{if(e.originalEvent&&e.originalEvent.stopPropagation)e.originalEvent.stopPropagation();}catch(x){}"
        "post({type:'valve-select',cfg:CFG,valve:v});mk.openPopup();});"
        "mk.on('dragend',function(){var p=mk.getLatLng();v.lon=+p.lng.toFixed(6);v.lat=+p.lat.toFixed(6);"
        "mk.setPopupContent(infoHtml(v));mk.openPopup();"
        "post({type:'valve-drag',cfg:CFG,valve_id:v.id,lon:v.lon,lat:v.lat});});"
        "});"
        "window.focusValve=function(id){var m=marks[id];if(!m)return false;"
        "try{mp.setView(m.getLatLng(),Math.max(mp.getZoom(),17));m.openPopup();}catch(x){}"
        "return true;};"
        "mp.on('click',function(e){"
        "try{var t=e.originalEvent&&e.originalEvent.target;"
        "if(t&&t.closest&&t.closest('.valve-marker'))return;}catch(x){}"
        "post({type:'valve-map-click',lon:e.latlng.lng,lat:e.latlng.lat});});"
        "});"
    ) + "</script>"


def _valve_pick_js():
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;"
        "mp.on('click',function(e){try{window.top.postMessage("
        "{type:'valve-map-click',lon:e.latlng.lng,lat:e.latlng.lat},'*');}catch(x){}});"
        "});"
    ) + "</script>"


def _other_pick_js():
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;"
        "mp.on('click',function(e){try{window.top.postMessage("
        "{type:'other-map-click',lon:e.latlng.lng,lat:e.latlng.lat},'*');}catch(x){}});"
        "});"
    ) + "</script>"


def _zone_pick_js():
    return "<script>" + (
        "window.addEventListener('load',function(){"
        "window.zonePickArmed=false;"
        "window.setZonePick=function(v){window.zonePickArmed=!!v;};"
        "var mp=null;for(var k in window){"
        "if(/^map_/.test(k)&&window[k]&&window[k].eachLayer){mp=window[k];break;}}"
        "if(!mp)return;"
        "mp.on('click',function(e){if(!window.zonePickArmed)return;"
        "try{window.top.postMessage({type:'zone-pick',lon:e.latlng.lng,lat:e.latlng.lat},'*');}catch(x){}});"
        "});"
    ) + "</script>"


def _zone_label(name):
    """Permanent badge glued on a zone centroid (name always visible)."""
    return (
        "<div style=\"font-family:Comfortaa,'Segoe UI',sans-serif;font-size:11px;"
        "font-weight:700;color:#fff;background:rgba(7,11,20,.68);"
        "border:1px solid rgba(255,255,255,.5);border-radius:8px;"
        "padding:1px 7px;white-space:nowrap;\">{n}</div>"
    ).format(n=_html.escape(str(name)))


def _sector_color_map(cfg):
    # generous palette so sectors stay identifiable
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    return {s["idx"]: palette[(s["idx"] - 1) % len(palette)] for s in cfg["sectors"]}


def map_sector(plan, cfg, sector, valves=True, pipes=True):
    """Sector detail map. Zones step uses valves=False, pipes=False so valves
    and piping only appear from their own steps onward."""
    lay = Layers()
    zones = sorted(sector.get("zones", []), key=lambda z: z["idx"])
    for i, z in enumerate(zones):
        lay.polygon(z["poly"], _ti("zone", name=z["name"], area=z["area_m2"]),
                    _ZONE_COLORS[i % len(_ZONE_COLORS)], 0.18, weight=2)

    if pipes:
        pr = cfg["pipes"]["principal"]
        lay.line(pr["line"], _ti("principal"), "#0b8a6f", 4)
        for maj in cfg["pipes"]["majors"]:
            if maj["zone"].startswith(sector["name"] + "-"):
                lay.line(maj["line"], _ti("major63", zone=maj["zone"]), "#377eb8", 3)
        for mn in cfg["pipes"]["minors"]:
            if mn["zone"].startswith(sector["name"] + "-"):
                lay.line(mn["line"], _ti("minor", zone=mn["zone"]), "#4daf4a", 2, dash="4, 2")
    if valves:
        for v in cfg["valves"]:
            if v["zone"].startswith(sector["name"] + "-") or v.get("sector") == sector["name"]:
                if v.get("kind") == "principal":
                    lay.marker(v["lon"], v["lat"], _ti("valve90", zone=v.get("sector") or v["zone"]), "red", radius=9)
                else:
                    lay.marker(v["lon"], v["lat"], _ti("valve32", zone=v["zone"]), "orange", radius=7)
    _marker(plan, lay, "basin", plan["basin"]["lon"], plan["basin"]["lat"], "brown", 11)
    _marker(plan, lay, "water", plan["water"]["lon"], plan["water"]["lat"], "blue", 8)
    lay.dashed(plan["land"], _ti("land_boundary"), "#333333", 1)
    nm = sector["centroid"]
    lay.marker(nm.x, nm.y, _ti("sector", name=sector["name"], area=sector["area_m2"]),
               "#111111", radius=3)
    center = [sector["centroid"].y, sector["centroid"].x]
    m = build(lay, center, 18)
    for z in zones:
        c = z["centroid"]
        folium.map.Marker(
            [c.y, c.x],
            icon=folium.DivIcon(html=_zone_label(z["name"])),
        ).add_to(m)
    m.get_root().html.add_child(folium.Element(_zone_pick_js()))
    return to_html(m)