"""Farm Simulator - part 1 web app (Flask).

Upload a KML/CSV of the land boundaries + water point, then get:
basin, sectorisations, zonage, valves and the piping layout.
"""
import os
import pickle
import uuid

from flask import Flask, abort, render_template, request

from core import engine, i18n, mapper, parser

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    btcfg=i18n.btcfg,
    i18n_css=i18n.css,
    version=app_version(),
)

WORKS = {}  # token -> analyse() result


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

    WORKS[token] = plan
    with open(os.path.join(UPLOAD_DIR, token + ".pkl"), "wb") as fh:
        pickle.dump(plan, fh)
    return render_view(plan, token)


def render_view(plan, token):
    cfg_maps = {}
    for cfg in plan["configs"]:
        cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
    return render_template(
        "result.html",
        token=token,
        plan=plan,
        cfg_maps=cfg_maps,
        basin_map=mapper.map_basin(plan),
    )


@app.route("/view/<token>/<int:cfgid>")
def view_config(token, cfgid):
    plan = get_plan(token)
    cfg = get_config(plan, cfgid)
    engine.extend(plan, cfgid)
    ov = mapper.map_config_overview(plan, cfg)
    per_sector = {}
    for s in cfg["sectors"]:
        per_sector[s["name"]] = mapper.map_sector(plan, cfg, s)
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
    detail = mapper.map_sector(plan, cfg, sector)
    return render_template(
        "sector.html",
        token=token, plan=plan, cfg=cfg,
        sector=sector, detail=detail,
        legend=BUILD_LEGEND,
    )


def get_plan(token):
    plan = WORKS.get(token)
    if plan is not None:
        return plan
    fp = os.path.join(UPLOAD_DIR, token + ".pkl")
    if os.path.exists(fp):
        with open(fp, "rb") as fh:
            plan = pickle.load(fh)
        WORKS[token] = plan
        return plan
    abort(404)


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
    app.run(host="127.0.0.1", port=8501, debug=True)