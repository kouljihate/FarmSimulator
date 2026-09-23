"""Farm Simulator - part 1 web app (Flask, single-URL SPA).

The whole UI lives on ONE url (``/``): the shell page holds the tab bar and
every interaction (upload, load, basin edits, sector ops, config overview)
is a POST to ``/`` returning JSON. Tab bodies are server-rendered HTML
fragments injected in place - the browser never leaves ``/``.
"""
import os
import re
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from core import engine, i18n, mapper, parser, storage

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")

STORE = storage.get_store()

# Bump when cached map artwork changes shape: older stored maps are regenerated.
MAPS_V = 5


def app_version():
    try:
        with open(os.path.join(BASE, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "?"


def fmt_dt(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def natsort(sectors):
    """Sectors sorted by name, A-Z case-insensitive with natural numbers."""
    def key(s):
        return [int(t) if t.isdigit() else t.lower()
                for t in re.split(r"(\d+)", s.get("name") or "")]
    return sorted(sectors or [], key=key)


def _pt(g):
    return {"lon": round(float(g.x), 6), "lat": round(float(g.y), 6)}


def _basin_summary(plan):
    b = plan.get("basin") or {}
    me = b.get("max_elev") or {}
    return {
        "lon": b.get("lon"),
        "lat": b.get("lat"),
        "z": b.get("z"),
        "has_elev": b.get("has_elev"),
        "dist_water_m": b.get("dist_water_m"),
        "max_elev": {"lon": me.get("lon"), "lat": me.get("lat"), "z": me.get("z")} if me else None,
    }


def _sector_summary(s):
    return {
        "idx": s.get("idx"),
        "name": s.get("name"),
        "area_m2": s.get("area_m2"),
        "centroid": _pt(s["centroid"]) if s.get("centroid") is not None else None,
        "entry": _pt(s["entry"]) if s.get("entry") is not None else None,
        "zone_angle": s.get("zone_angle"),
        "zones": [{"name": z.get("name"), "area_m2": z.get("area_m2")}
                  for z in s.get("zones") or []],
    }


def _cfg_totals(cfg):
    pipes = cfg.get("pipes") or {}
    princ = (pipes.get("principal") or {}).get("len_m", 0.0)
    majors = sum(m.get("len_m", 0.0) for m in pipes.get("majors", []) or [])
    minors = sum(m.get("len_m", 0.0) for m in pipes.get("minors", []) or [])
    customs = sum(m.get("len_m", 0.0) for m in pipes.get("customs", []) or [])
    n_p = sum(1 for v in cfg.get("valves", []) or [] if v.get("kind") == "principal")
    n_s = sum(1 for v in cfg.get("valves", []) or [] if v.get("kind") != "principal")
    return {"principal_m": princ, "majors_m": majors, "minors_m": minors,
            "total_m": princ + majors + minors + customs,
            "n_principal": n_p, "n_secondary": n_s,
            "n_zones": len(cfg.get("zones", []) or [])}


def plan_summary(plan):
    return {
        "name": plan.get("name", "Untitled plot"),
        "land_area_m2": plan.get("land_area_m2"),
        "n_boundaries": len(plan.get("all_boundaries") or []),
        "water": dict(plan.get("water") or {}),
        "basin": _basin_summary(plan),
        "existing_sectors": bool(plan.get("existing_sectors")),
        "other_elements": [dict(e) for e in (plan.get("other_elements") or [])],
        "simulation": dict(plan.get("simulation") or {}),
        "boundaries": [
            {"name": b.get("name"), "description": b.get("description") or "",
             "is_land": bool(b.get("is_land")), "area_m2": b.get("area_m2")}
            for b in (plan.get("boundaries") or [])
        ],
        "water_points": [dict(w) for w in (plan.get("water_points") or [])],
        "n_water_points": plan.get("n_water_points", len(plan.get("water_points") or [])),
        "configs": [{
            "id": c.get("id"),
            "name": c.get("name"),
            "n_sectors": c.get("n_sectors"),
            "zones_confirmed": bool(c.get("zones_confirmed")),
            "totals": _cfg_totals(c),
            "sectors": [_sector_summary(s) for s in c.get("sectors") or []],
        } for c in plan.get("configs") or []],
    }


def _norm_name(name):
    return (name or "untitled plot").strip().lower()


def _dedup_runs(runs):
    best = {}
    for r in runs or []:
        k = _norm_name(r.get("name"))
        if k not in best or (r.get("updated_at") or 0) > (best[k].get("updated_at") or 0):
            best[k] = r
    out = sorted(best.values(), key=lambda r: r.get("updated_at") or 0, reverse=True)
    for r in out:
        r["updated_str"] = fmt_dt(r.get("updated_at"))
    return out


def _token_for_land(name, exclude=None):
    for r in STORE.list_runs(limit=200):
        if _norm_name(r.get("name")) == _norm_name(name) and r.get("token") != exclude:
            return r.get("token")
    return None


def _persist(token, plan, maps=None):
    if maps is None:
        doc = STORE.load(token) or {}
        keep = {k: doc.get(k) for k in ("basin_map", "cfg_maps", "overview_maps",
                                        "sector_maps", "other_maps", "maps_v")
                if doc.get(k) is not None}
        STORE.save(token, plan, keep)
    else:
        STORE.save(token, plan, maps)


def _overview_ctx(token, plan, cfg, only_sector=None, only_pipe_sector=None):
    engine.extend(plan, cfg["id"])
    if only_sector is not None and only_sector not in {
            s.get("name") for s in cfg.get("sectors", [])}:
        only_sector = None
    if only_pipe_sector is not None and only_pipe_sector not in {
            s.get("name") for s in cfg.get("sectors", [])}:
        only_pipe_sector = None
    doc = STORE.load(token)
    ov_maps = dict((doc or {}).get("overview_maps") or {})
    sector_maps = dict((doc or {}).get("sector_maps") or {})
    other_maps = dict((doc or {}).get("other_maps") or {})
    if (doc or {}).get("maps_v") != MAPS_V:
        for store in (ov_maps, sector_maps, other_maps):
            store.pop(cfg["id"], None)
            store.pop(str(cfg["id"]), None)
    ov = ov_maps.get(cfg["id"])
    if ov is None:
        ov = mapper.map_config_overview(plan, cfg)
        ov_maps[cfg["id"]] = ov
    per_sector = dict(sector_maps.get(cfg["id"]) or {})
    for s in cfg["sectors"]:
        if s["name"] not in per_sector:
            per_sector[s["name"]] = mapper.map_sector(plan, cfg, s,
                                                      valves=False, pipes=False)
    sector_maps[cfg["id"]] = per_sector
    other = other_maps.get(cfg["id"])
    if other is None:
        other = mapper.map_other_elements(plan, cfg)
        other_maps[cfg["id"]] = other
    STORE.save_maps(token, {"overview_maps": ov_maps,
                            "sector_maps": sector_maps,
                            "other_maps": other_maps,
                            "maps_v": MAPS_V})
    _persist(token, plan)
    sim = engine.compute_simulation(plan, cfg, **(plan.get("simulation") or {}))
    return {"token": token, "plan": plan, "cfg": cfg,
            "overview_map": ov, "per_sector": per_sector,
            "other_map": other,
            "valves_map": mapper.map_config_valves(plan, cfg, only_sector),
            "selected_sector": only_sector,
            "pipes_map": mapper.map_config_pipes(plan, cfg, only_pipe_sector),
            "selected_pipe_sector": only_pipe_sector,
            "tree_codes": engine.TREE_TYPES,
            "sim": sim}


def _overview_fragments(ctx):
    return {
        "zones_html": render_template("_zones_result.html", **ctx),
        "valves_html": render_template("_valves_result.html", **ctx),
        "pipes_html": render_template("_pipes_result.html", **ctx),
        "other_html": render_template("_other_result.html", **ctx),
        "trees_html": render_template("_trees_result.html", **ctx),
        "sim_html": render_template("_simulation_result.html", **ctx),
        "final_html": render_template("_final_result.html", **ctx),
    }


def _full_payload(token, plan, save=True):
    cfg_maps = {}
    for cfg in plan["configs"]:
        cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
    basin_map = mapper.map_basin(plan)
    if save:
        _persist(token, plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})
    return {
        "ok": True,
        "token": token,
        "plan": plan_summary(plan),
        "basin_html": render_template("_basin_result.html", token=token, plan=plan,
                                      basin_map=basin_map),
        "sectors_html": render_template("_sectors_result.html", token=token, plan=plan,
                                        cfg_maps=cfg_maps),
        "upload_html": render_template("_upload_card.html", plan=plan),
    }


def _err(msg):
    return jsonify(ok=False, error=str(i18n.err(msg)))


def _get_plan(token):
    plan = STORE.get_plan(token)
    return plan


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

app.jinja_env.globals.update(
    t=i18n.t,
    tl=i18n.tl,
    bt=i18n.bt,
    bi=i18n.bi,
    bv=i18n.bv,
    bvfmt=i18n.bvfmt,
    ts=i18n.ts,
    tsf=i18n.tsf,
    btcfg=i18n.btcfg,
    i18n_css=i18n.css,
    version=app_version(),
    fmt_dt=fmt_dt,
)
app.jinja_env.filters["natsort"] = natsort


@app.context_processor
def inject_runs():
    return {"runs": _dedup_runs(STORE.list_runs())}


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    f = request.files.get("file")
    if f is not None and f.filename:
        tmp = uuid.uuid4().hex[:12]
        dest = os.path.join(UPLOAD_DIR, tmp + "_" + os.path.basename(f.filename))
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
        except Exception as exc:  # noqa: BLE001 - surface parsing errors as JSON
            if os.path.exists(dest):
                os.remove(dest)
            return _err(str(exc))
        if os.path.exists(dest):
            os.remove(dest)
        token = _token_for_land(plan.get("name")) or uuid.uuid4().hex[:12]
        return jsonify(_full_payload(token, plan))

    data = request.get_json(silent=True) or {}
    op = data.get("op")

    if op == "list_runs":
        return jsonify(ok=True, runs=_dedup_runs(STORE.list_runs()))

    if op == "delete_run":
        token = data.get("token")
        plan = _get_plan(token)
        if plan is None:
            return _err("Run not found.")
        try:
            STORE.delete(token)
        except AttributeError:
            pass
        return jsonify(ok=True, runs=_dedup_runs(STORE.list_runs()))

    if op == "load":
        plan = _get_plan(data.get("token"))
        if plan is None:
            return _err("Run not found.")
        return jsonify(_full_payload(data.get("token"), plan, save=False))

    if op == "basin":
        plan = _get_plan(data.get("token"))
        if plan is None:
            return _err("Run not found.")
        try:
            lon = float(data.get("lon"))
            lat = float(data.get("lat"))
        except (TypeError, ValueError):
            ok, msg = False, "Invalid coordinates."
        else:
            ok, msg = engine.set_basin(plan, lon, lat)
        cfg_maps = {}
        for cfg in plan["configs"]:
            cfg_maps[cfg["id"]] = mapper.map_config_preview(plan, cfg)
        basin_map = mapper.map_basin(plan)
        if ok:
            _persist(data.get("token"), plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})
        if not ok:
            return jsonify(ok=False, error_html=str(i18n.err(msg)))
        return jsonify(
            ok=True,
            basin=plan["basin"] and {
                "lon": plan["basin"]["lon"],
                "lat": plan["basin"]["lat"],
                "dist_water_m": plan["basin"]["dist_water_m"],
            },
            basin_map=basin_map,
            sectors_html=render_template(
                "_sectors_result.html", token=data.get("token"), plan=plan,
                cfg_maps=cfg_maps),
            plan=plan_summary(plan),
        )

    if op == "sector_coords":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        sector = next((s for s in cfg["sectors"] if s["idx"] == data.get("idx")), None)
        if sector is None:
            return _err("Sector not found.")
        poly = sector["poly"]
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        ring = [[round(float(x), 8), round(float(y), 8)] for x, y in poly.exterior.coords]
        return jsonify(ok=True, idx=data.get("idx"), ring=ring)

    if op == "sector_action":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        ok, msg = engine.apply_sector_op(
            plan, cfg,
            data.get("action", ""),
            idx=data.get("idx"),
            idx2=data.get("idx2"),
            name=data.get("name"),
            ring=data.get("ring"),
        )
        if not ok:
            return jsonify(ok=False, error=str(i18n.err(msg)))
        cfg_maps = {}
        for c in plan["configs"]:
            cfg_maps[c["id"]] = mapper.map_config_preview(plan, c)
        doc = STORE.load(data.get("token"))
        basin_map = (doc or {}).get("basin_map")
        _persist(data.get("token"), plan, {"basin_map": basin_map, "cfg_maps": cfg_maps})
        ov_maps = dict((doc or {}).get("overview_maps") or {})
        sector_maps = dict((doc or {}).get("sector_maps") or {})
        other_maps = dict((doc or {}).get("other_maps") or {})
        for key, store in ((data.get("cfgid"), ov_maps), (str(data.get("cfgid")), ov_maps),
                           (data.get("cfgid"), sector_maps), (str(data.get("cfgid")), sector_maps),
                           (data.get("cfgid"), other_maps), (str(data.get("cfgid")), other_maps)):
            store.pop(key, None)
        STORE.save_maps(data.get("token"), {"overview_maps": ov_maps, "sector_maps": sector_maps,
                                            "other_maps": other_maps})
        return jsonify(
            ok=True,
            sectors_html=render_template(
                "_sectors_result.html", token=data.get("token"), plan=plan,
                cfg_maps=cfg_maps),
            plan=plan_summary(plan),
        )

    if op == "zone_action":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        ok, msg = engine.apply_zone_op(
            plan, cfg, data.get("action", ""),
            sector_idx=data.get("sector_idx"), zone_idx=data.get("zone_idx"),
            zone_name=data.get("zone_name"), name=data.get("name"),
            x1=data.get("x1"), y1=data.get("y1"),
            x2=data.get("x2"), y2=data.get("y2"),
            zone_name2=data.get("zone_name2"),
            zone_names=data.get("zone_names"),
        )
        if not ok:
            return jsonify(ok=False, error=str(i18n.err(msg)))
        doc = STORE.load(data.get("token"))
        ov_maps = dict((doc or {}).get("overview_maps") or {})
        sector_maps = dict((doc or {}).get("sector_maps") or {})
        other_maps = dict((doc or {}).get("other_maps") or {})
        for key, store in ((data.get("cfgid"), ov_maps), (str(data.get("cfgid")), ov_maps),
                           (data.get("cfgid"), sector_maps), (str(data.get("cfgid")), sector_maps),
                           (data.get("cfgid"), other_maps), (str(data.get("cfgid")), other_maps)):
            store.pop(key, None)
        STORE.save_maps(data.get("token"), {"overview_maps": ov_maps, "sector_maps": sector_maps,
                                            "other_maps": other_maps})
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    if op == "valve_action":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        ok, msg = engine.apply_valve_op(
            plan, cfg, data.get("action", ""),
            valve_id=data.get("valve_id"), kind=data.get("kind"),
            lon=data.get("lon"), lat=data.get("lat"),
            sector=data.get("sector"), zone=data.get("zone"),
        )
        if not ok:
            return jsonify(ok=False, error=str(i18n.err(msg)))
        doc = STORE.load(data.get("token"))
        ov_maps = dict((doc or {}).get("overview_maps") or {})
        sector_maps = dict((doc or {}).get("sector_maps") or {})
        other_maps = dict((doc or {}).get("other_maps") or {})
        for key, store in ((data.get("cfgid"), ov_maps), (str(data.get("cfgid")), ov_maps),
                           (data.get("cfgid"), sector_maps), (str(data.get("cfgid")), sector_maps),
                           (data.get("cfgid"), other_maps), (str(data.get("cfgid")), other_maps)):
            store.pop(key, None)
        STORE.save_maps(data.get("token"), {"overview_maps": ov_maps, "sector_maps": sector_maps,
                                            "other_maps": other_maps})
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    if op == "pipe_action":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        ok, msg = engine.apply_pipe_op(
            plan, cfg, data.get("action", ""),
            pipe_id=data.get("pipe_id"), diameter=data.get("diameter"),
            sector=data.get("sector"), zone=data.get("zone"),
            path=data.get("path"),
        )
        if not ok:
            return jsonify(ok=False, error=str(i18n.err(msg)))
        doc = STORE.load(data.get("token"))
        ov_maps = dict((doc or {}).get("overview_maps") or {})
        sector_maps = dict((doc or {}).get("sector_maps") or {})
        other_maps = dict((doc or {}).get("other_maps") or {})
        for key, store in ((data.get("cfgid"), ov_maps), (str(data.get("cfgid")), ov_maps),
                           (data.get("cfgid"), sector_maps), (str(data.get("cfgid")), sector_maps),
                           (data.get("cfgid"), other_maps), (str(data.get("cfgid")), other_maps)):
            store.pop(key, None)
        STORE.save_maps(data.get("token"), {"overview_maps": ov_maps, "sector_maps": sector_maps,
                                            "other_maps": other_maps})
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    if op == "other_add":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        kind = (data.get("kind") or "pressure_reducer").strip()
        if kind not in engine.OTHER_KINDS:
            kind = "pressure_reducer"
        try:
            lon = float(data.get("lon"))
            lat = float(data.get("lat"))
        except (TypeError, ValueError):
            return jsonify(ok=False, error=str(i18n.err("Invalid coordinates.")))
        verdict = engine.analyse_other_element(plan, cfg, kind, lon, lat)
        el = {"id": uuid.uuid4().hex[:8], "kind": kind, "lon": lon, "lat": lat,
              "size": (data.get("size") or "").strip()[:24],
              "note": (data.get("note") or "").strip()[:200],
              "necessary": verdict["necessary"], "verdict": verdict["verdict"],
              "suggestion": verdict["suggestion"]}
        plan.setdefault("other_elements", []).append(el)
        doc = STORE.load(data.get("token"))
        other_maps = dict((doc or {}).get("other_maps") or {})
        other_maps.pop(data.get("cfgid"), None)
        other_maps.pop(str(data.get("cfgid")), None)
        STORE.save_maps(data.get("token"), {"other_maps": other_maps})
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan),
                     element=el)
        return jsonify(frags)

    if op == "other_remove":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        plan["other_elements"] = [e for e in (plan.get("other_elements") or [])
                                  if e.get("id") != data.get("id")]
        doc = STORE.load(data.get("token"))
        other_maps = dict((doc or {}).get("other_maps") or {})
        other_maps.pop(data.get("cfgid"), None)
        other_maps.pop(str(data.get("cfgid")), None)
        STORE.save_maps(data.get("token"), {"other_maps": other_maps})
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    if op == "tree_save":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        ok, msg = engine.apply_tree_op(plan, cfg, data.get("trees"))
        if not ok:
            return jsonify(ok=False, error=str(i18n.err(msg)))
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    if op == "sim_save":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        engine.extend(plan, data.get("cfgid"))
        if data.get("use_ai"):
            area_ha = (plan.get("land_area_m2") or 0.0) / 10000.0
            plan["simulation"] = {"years": int(data.get("years") or 10),
                                  "capex": round(2500 * area_ha + 1200, 2),
                                  "annual_cost": round(600 * area_ha + 300, 2),
                                  "annual_revenue": round(2600 * area_ha + 400, 2),
                                  "crop": data.get("crop") or "vegetables"}
        else:
            plan["simulation"] = {"years": data.get("years"),
                                  "capex": data.get("capex"),
                                  "annual_cost": data.get("annual_cost"),
                                  "annual_revenue": data.get("annual_revenue"),
                                  "crop": data.get("crop") or "vegetables"}
        ctx = _overview_ctx(data.get("token"), plan, cfg)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan),
                     sim=ctx["sim"])
        return jsonify(frags)

    if op == "overview":
        plan = _get_plan(data.get("token"))
        cfg = next((c for c in (plan or {}).get("configs", [])
                    if c["id"] == data.get("cfgid")), None)
        if plan is None or cfg is None:
            return _err("Run not found.")
        ctx = _overview_ctx(data.get("token"), plan, cfg,
                              data.get("sector") or None,
                              data.get("psector") or None)
        frags = _overview_fragments(ctx)
        frags.update(ok=True, cfgid=data.get("cfgid"), plan=plan_summary(plan))
        return jsonify(frags)

    return _err("Unknown operation.")


if __name__ == "__main__":
    try:
        app.run(host="127.0.0.1", port=8501, debug=True)
    except KeyboardInterrupt:
        print('Exiting...')
