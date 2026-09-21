"""Farm Simulator - part 1 web app (Flask).

Upload a KML/CSV of the land boundaries + water point, then get:
basin, sectorisations, zonage, valves and the piping layout.
"""
import os
import uuid

from flask import Flask, abort, jsonify, render_template, request

from core import engine, i18n, mapper, parser, storage

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")

STORE = storage.get_store()


def app_version():
    try:
        with open(os.path.join(BASE, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "?"


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

app.jinja_env.globals.update(
    t=i18n.t,
    tl=i18n.tl,
    bt=i18n.bt,
    bi=i18n.bi,
    bv=i18n.bv,
    ts=i18n.ts,
    tsf=i18n.tsf,
    btcfg=i18n.btcfg,
    i18n_css=i18n.css,
    version=app_version(),
)


@app.context_processor
def inject_runs():
    return {"runs": STORE.list_runs()}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if f is None or not f.filename:
        return render_template("index.html", error=i18n.err("Please choose a KML or CSV file first."))

    token = uuid.uuid4().hex[:12]
    dest = os.path.join(UPLOAD_DIR, token + "_" + os.path.basename(f.filename))
    f.save(dest)

    try:
        parsed = parser.load_file(dest)
        if not parsed.get("polygons"):
            raise ValueError("No boundary polygon found in the upload.")
        if not parsed.get("water_points"):
            raise ValueError(
                'No water point found. Mark it in your file (KML Point or CSV row with type "water").'
            )
        plan = engine.analyse(parsed)
    except Exception as exc:  # noqa: BLE001 - surface parsing errors to the page
        if os.path.exists(dest):
            os.remove(dest)
        return render_template("index.html", error=i18n.err(str(exc)))

    cfg_maps = {}
    for cfg in plan["configs"]:
        cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
    basin_map = mapper.map_basin(plan)
    STORE.save(token, plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})
    return render_template(
        "index.html",
        token=token,
        plan=plan,
        cfg_maps=cfg_maps,
        basin_map=basin_map,
    )


@app.route("/load")
def load_runs():
    return render_template("index.html")


@app.route("/load/<token>")
def load_run(token):
    doc = STORE.load(token)
    if doc is None:
        abort(404)
    plan = doc["plan"]
    cfg_maps = doc.get("cfg_maps") or {}
    basin_map = doc.get("basin_map")
    stale = (not basin_map) or (not cfg_maps) or any(
        "selectSector" not in (cfg_maps[v] or "") for v in cfg_maps
    )
    if stale:
        cfg_maps = {}
        for cfg in plan["configs"]:
            cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
        if not basin_map:
            basin_map = mapper.map_basin(plan)
        STORE.save_maps(token, {"basin_map": basin_map, "cfg_maps": cfg_maps})
    return render_template(
        "index.html",
        token=token,
        plan=plan,
        cfg_maps=cfg_maps,
        basin_map=basin_map,
    )


@app.route("/basin/<token>", methods=["POST"])
def edit_basin(token):
    plan = get_plan(token)
    try:
        lon = float(request.form.get("lon"))
        lat = float(request.form.get("lat"))
    except (TypeError, ValueError):
        ok = False
        msg = "Invalid coordinates."
    else:
        ok, msg = engine.set_basin(plan, lon, lat)

    cfg_maps = {}
    for cfg in plan["configs"]:
        cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
    basin_map = mapper.map_basin(plan)

    if ok:
        STORE.save(token, plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            ok=ok,
            error_html=i18n.err(msg) if not ok else None,
            basin={
                "lon": plan["basin"]["lon"],
                "lat": plan["basin"]["lat"],
                "dist_water_m": plan["basin"]["dist_water_m"],
            },
            basin_map=basin_map,
            sectors=render_template(
                "_sectors_result.html", token=token, plan=plan, cfg_maps=cfg_maps
            ),
        )

    return render_template(
        "index.html",
        token=token,
        plan=plan,
        cfg_maps=cfg_maps,
        basin_map=basin_map,
        error=i18n.err(msg) if not ok else None,
    )


@app.route("/sectors/<token>/<int:cfgid>/<int:sidx>/coords")
def sector_coords(token, cfgid, sidx):
    plan = get_plan(token)
    cfg = get_config(plan, cfgid)
    sector = next((s for s in cfg["sectors"] if s["idx"] == sidx), None)
    if sector is None:
        abort(404)
    poly = sector["poly"]
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    ring = [[round(float(x), 8), round(float(y), 8)] for x, y in poly.exterior.coords]
    return jsonify(ok=True, idx=sidx, ring=ring)


@app.route("/sectors/<token>/<int:cfgid>/action", methods=["POST"])
def sector_action(token, cfgid):
    plan = get_plan(token)
    cfg = get_config(plan, cfgid)
    data = request.get_json(silent=True) or {}
    ok, msg = engine.apply_sector_op(
        plan, cfg,
        data.get("action", ""),
        idx=data.get("idx"),
        idx2=data.get("idx2"),
        name=data.get("name"),
        ring=data.get("ring"),
    )
    if not ok:
        return jsonify(ok=False, error=i18n.err(msg))

    cfg_maps = {}
    for c in plan["configs"]:
        cfg_maps[c["id"]] = mapper.map_config_preview(plan, c)
    doc = STORE.load(token)
    basin_map = (doc or {}).get("basin_map")
    STORE.save(token, plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})

    ov_maps = dict((doc or {}).get("overview_maps") or {})
    sector_maps = dict((doc or {}).get("sector_maps") or {})
    for key, store in ((cfgid, ov_maps), (str(cfgid), ov_maps),
                       (cfgid, sector_maps), (str(cfgid), sector_maps)):
        store.pop(key, None)
    STORE.save_maps(token, {"overview_maps": ov_maps, "sector_maps": sector_maps})

    return jsonify(
        ok=True,
        sectors=render_template(
            "_sectors_result.html", token=token, plan=plan, cfg_maps=cfg_maps
        ),
    )


@app.route("/view/<token>/<int:cfgid>")
def view_config(token, cfgid):
    plan = get_plan(token)
    cfg = get_config(plan, cfgid)
    engine.extend(plan, cfgid)

    doc = STORE.load(token)
    ov_maps = dict((doc or {}).get("overview_maps") or {})
    sector_maps = dict((doc or {}).get("sector_maps") or {})

    ov = ov_maps.get(cfgid)
    if ov is None:
        ov = mapper.map_config_overview(plan, cfg)
        ov_maps[cfgid] = ov
    per_sector = dict(sector_maps.get(cfgid) or {})
    for s in cfg["sectors"]:
        if s["name"] not in per_sector:
            per_sector[s["name"]] = mapper.map_sector(plan, cfg, s)
    sector_maps[cfgid] = per_sector

    STORE.save_maps(token, {"overview_maps": ov_maps, "sector_maps": sector_maps})
    return render_template(
        "config.html",
        token=token, plan=plan, cfg=cfg,
        overview=ov, per_sector=per_sector,
        legend=BUILD_LEGEND,
    )


@app.route("/sector/<token>/<int:cfgid>/<int:sidx>")
def sector_detail(token, cfgid, sidx):
    plan = get_plan(token)
    cfg = get_config(plan, cfgid)
    engine.extend(plan, cfgid)
    sector = next((s for s in cfg["sectors"] if s["idx"] == sidx), None)
    if sector is None:
        abort(404)

    doc = STORE.load(token)
    sector_maps = dict((doc or {}).get("sector_maps") or {})
    per_sector = dict(sector_maps.get(cfgid) or {})
    detail = per_sector.get(sector["name"])
    if detail is None:
        detail = mapper.map_sector(plan, cfg, sector)
        per_sector[sector["name"]] = detail
        sector_maps[cfgid] = per_sector
        STORE.save_maps(token, {"sector_maps": sector_maps})

    return render_template(
        "sector.html",
        token=token, plan=plan, cfg=cfg,
        sector=sector, detail=detail,
        legend=BUILD_LEGEND,
    )


def get_plan(token):
    plan = STORE.get_plan(token)
    if plan is None:
        abort(404)
    return plan


def get_config(plan, cfgid):
    cfg = next((c for c in plan["configs"] if c["id"] == cfgid), None)
    if cfg is None:
        abort(404)
    return cfg


BUILD_LEGEND = [
    ("Boundary", "#333333", "polygon"),
    ("Water point", "blue", "marker"),
    ("Basin (recommended)", "brown", "marker"),
    ("Max elevation", "green", "marker"),
    ("Sector (S1, S2, ...)", "#1f77b4", "polygon"),
    ("Zone (Z1, Z2, Z3)", "#ff7f0e", "polygon"),
    ("Valve 50mm", "red", "marker"),
    ("Principal pipe 90mm", "#0b8a6f", "line"),
    ("Major pipe 50mm", "#377eb8", "line"),
    ("Minor pipe 32mm", "#4daf4a", "line"),
]


if __name__ == "__main__":
    try:
        app.run(host="127.0.0.1", port=8501, debug=True)
    except KeyboardInterrupt:
        print('Exiting...')