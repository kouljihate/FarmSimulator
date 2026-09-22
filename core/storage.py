"""Persistence for analysed plans and the generated maps.

Primary store is MongoDB (`MONGO_URI` / `MONGO_DB` env vars, default
`mongodb://127.0.0.1:27017/farm_simulator`, collection `plans`). When MongoDB
is unreachable the app silently falls back to local pickles in `uploads/`, so
it keeps working offline.

Every stored record is keyed by the upload token and holds:
  plan          – the full plan dict (shapely geometries survive via pickle)
  basin_map     – the basin-tab folium HTML
  cfg_maps      – {cfg_id: sector preview HTML}
  overview_maps – {cfg_id: full overview HTML}   (saved on /view)
  sector_maps   – {cfg_id: {sector_name: HTML}}  (saved on /sector)
"""
import os
import pickle
import time

try:
    import bson
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure as _MongoDown
    HAS_MONGO = True
except Exception:  # noqa: BLE001 - driver optional
    HAS_MONGO = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.environ.get("MONGO_DB", "farm_simulator")
MONGO_COLL = "plans"

FULL_KEYS = ("basin_map", "cfg_maps", "overview_maps", "sector_maps")
_ID_MAP_KEYS = ("cfg_maps", "overview_maps", "sector_maps")


def _encode(maps):
    """Stringify the int keys of per-config map dicts for BSON/JSON storage."""
    out = {}
    for k, v in (maps or {}).items():
        out[k] = {str(sk): sv for sk, sv in v.items()} if k in _ID_MAP_KEYS else v
    return out


def _decode(doc):
    """Restore int keys of per-config map dicts read back from storage."""
    for k in _ID_MAP_KEYS:
        raw = doc.get(k) or {}
        doc[k] = {int(sk): sv for sk, sv in raw.items()}
    return doc


class MongoStore:
    """MongoDB-backed store. The plan is pickled into a BSON binary so shapely
    geometry objects survive the round-trip."""

    def __init__(self, uri=MONGO_URI, db=MONGO_DB, timeout_ms=3000):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self.col = self.client[db][MONGO_COLL]

    def ping(self):
        self.client.admin.command("ping")
        return True

    def _row(self, token):
        doc = self.col.find_one({"_id": token})
        if doc is None:
            return None
        doc["plan"] = pickle.loads(doc.pop("plan"))
        return _decode(doc)

    def get_plan(self, token):
        doc = self._row(token)
        return doc["plan"] if doc else None

    def load(self, token):
        return self._row(token)

    def save(self, token, plan, maps=None):
        attrs = _encode(maps)
        doc = {
            "_id": token,
            "name": plan.get("name", "Untitled plot"),
            "plan": bson.binary.Binary(pickle.dumps(plan, protocol=pickle.HIGHEST_PROTOCOL)),
            "updated_at": time.time(),
        }
        doc.update(attrs)
        self.col.replace_one({"_id": token}, doc, upsert=True)

    def save_maps(self, token, maps):
        if maps:
            self.col.update_one(
                {"_id": token},
                {"$set": dict(_encode(maps), updated_at=time.time())},
            )

    def list_runs(self, limit=50):
        rows = (
            self.col.find({}, {"_id": 1, "name": 1, "updated_at": 1})
            .sort("updated_at", -1)
            .limit(limit)
        )
        return [{
            "token": r["_id"],
            "name": r.get("name", "Untitled plot"),
            "updated_at": r.get("updated_at", 0.0),
        } for r in rows]


class FileStore:
    """Offline fallback: one pickle per token in uploads/ (plan + maps)."""

    def _fp(self, token):
        return os.path.join(UPLOAD_DIR, token + ".db")

    def _row(self, token):
        fp = self._fp(token)
        if os.path.exists(fp):
            with open(fp, "rb") as fh:
                row = pickle.load(fh)
            return _decode(row)
        return None

    def get_plan(self, token):
        row = self._row(token)
        if row is not None:
            return row["plan"]
        old = os.path.join(UPLOAD_DIR, token + ".pkl")
        if os.path.exists(old):
            with open(old, "rb") as fh:
                plan = pickle.load(fh)
            self.save(token, plan, {k: None for k in FULL_KEYS})
            return plan
        return None

    def load(self, token):
        return self._row(token)

    def save(self, token, plan, maps=None):
        row = {"name": plan.get("name", "Untitled plot"), "plan": plan, "updated_at": time.time()}
        row.update(_encode({k: maps.get(k) if maps else None for k in FULL_KEYS}))
        with open(self._fp(token), "wb") as fh:
            pickle.dump(row, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def save_maps(self, token, maps):
        row = self._row(token)
        if row is None:
            return
        row.update(_encode(maps))
        row["updated_at"] = time.time()
        with open(self._fp(token), "wb") as fh:
            pickle.dump(row, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def list_runs(self, limit=50):
        runs = []
        for fn in os.listdir(UPLOAD_DIR):
            if not fn.endswith(".db"):
                continue
            try:
                with open(os.path.join(UPLOAD_DIR, fn), "rb") as fh:
                    row = pickle.load(fh)
            except Exception:  # noqa: BLE001 - skip corrupt files
                continue
            runs.append({
                "token": fn[:-3],
                "name": row.get("name", "Untitled plot"),
                "updated_at": row.get("updated_at", 0.0),
            })
        runs.sort(key=lambda r: r["updated_at"], reverse=True)
        return runs[:limit]


def get_store():
    """Return a usable store: MongoDB when reachable, else the file fallback."""
    if HAS_MONGO:
        try:
            store = MongoStore()
            store.ping()
            return store
        except Exception:  # noqa: BLE001 - any connect/render failure -> fall back
            pass
    return FileStore()