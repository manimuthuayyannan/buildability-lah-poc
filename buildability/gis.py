import json, math, re, requests
from .config import PARCEL_LAYER, CONTOUR_LAYER, DEM_IMAGE, HEADERS, SR, FT_PER_M, FT2_PER_M2, ACRES_PER_FT2
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import HEADERS, DEFAULT_TIMEOUT, RETRY_TOTAL, RETRY_BACKOFF, USER_AGENT

# build a resilient session once
_session = requests.Session()
retry = Retry(
    total=RETRY_TOTAL,
    connect=RETRY_TOTAL,
    read=RETRY_TOTAL,
    backoff_factor=RETRY_BACKOFF,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods={"GET", "POST"},
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

_base_headers = {**HEADERS, "User-Agent": USER_AGENT}

def gget(url, **params):
    r = _session.get(url, params={"f": "json", **params},
                     headers=_base_headers, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()

def gpost(url, **params):
    r = _session.post(url, data={"f": "json", **params},
                      headers=_base_headers, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()

# ---- Address / APN search ----

def normalize_address(text):
    return re.sub(r"[^A-Za-z0-9 ]+", "", text).strip().upper()

def search_parcel_by_address(address):
    addr = normalize_address(address)
    tokens = addr.split()
    if len(tokens) < 2:
        raise ValueError("Address too short. Include house number and street name.")
    house, street = tokens[0], tokens[1]
    where = f"SITUS_HOUSE_NUMBER LIKE '{house}%' AND SITUS_STREET_NAME LIKE '{street}%'"
    js = gget(PARCEL_LAYER + "/query",
              where=where, outFields="*", returnGeometry="true", outSR=SR, resultRecordCount=5)
    feats = js.get("features", [])
    if not feats:
        raise ValueError(f"No parcel found for address: {address}")
    f = feats[0]
    return f["attributes"].get("APN"), f["geometry"], f["attributes"]

def search_parcel_by_apn(apn):
    js = gget(PARCEL_LAYER + "/query",
              where=f"APN='{apn}'", outFields="*", returnGeometry="true", outSR=SR)
    feats = js.get("features", [])
    if not feats:
        raise ValueError(f"No parcel for APN {apn}")
    f = feats[0]
    return f["geometry"], f["attributes"]

# ---- Geometry helpers ----

def ring_area_m2(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]; x2, y2 = ring[i+1]
        a += x1*y2 - x2*y1
    return abs(a) / 2.0

def parcel_area_m2(geom):
    if not geom or "rings" not in geom or not geom["rings"]:
        return 0.0
    total = 0.0
    for r in geom["rings"]:
        total += ring_area_m2(r)
    return total

def point_in_ring(x, y, ring):
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside

# ---- Contours ----

def detect_elev_field():
    meta = gget(CONTOUR_LAYER)
    candidates = ["ELEV", "ELEVATION", "CONTOUR", "INDEXELEV", "INDEX"]
    fields = {f["name"].upper(): f["name"] for f in meta.get("fields", [])}
    for c in candidates:
        if c in fields:
            return fields[c]
    return None

M2_TO_FT2 = 10.7639
M_TO_FT = 3.28084

def _polyline_length_m(geom: dict) -> float:
    total = 0.0
    # geometry: {"paths": [[[x1,y1],[x2,y2],...], [...]]}
    paths = (geom or {}).get("paths") or []
    for path in paths:
        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            total += math.hypot(x2 - x1, y2 - y1)
    return total

def contours_inside(parcel_geom: dict, layer_url: str, elev_field: str = None):
    """
    Return (features, total_len_m).
    We intentionally use returnGeometry=true and compute length from geometry
    so we don't depend on Shape_Length field naming.
    """
    params = {
        "where": "1=1" if not elev_field else f"{elev_field} IS NOT NULL",
        "outFields": "*" if elev_field else "OBJECTID",   # bring attrs if we need elevation
        "returnGeometry": "true",
        "geometry": json.dumps(parcel_geom),
        "geometryType": "esriGeometryPolygon",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": SR,
        "outSR": SR,
        "resultRecordCount": 2000,
    }
    js = arcgis_get(layer_url + "/query", params)
    feats = js.get("features", [])

    total_len_m = 0.0
    for f in feats:
        g = f.get("geometry")
        total_len_m += _polyline_length_m(g)

    return feats, total_len_m
def two_ft_subset(features, elev_field):
    if not features or not elev_field:
        return features or []
    out = []
    for f in features:
        try:
            z = float(f.get("attributes", {}).get(elev_field))
        except (TypeError, ValueError):
            z = None
        if z is not None and abs(z % 2.0) < 1e-6:
            out.append(f)
    return out

def contour_length_m(features):
    total_m = 0.0
    for f in features:
        sl = f.get("attributes", {}).get("Shape_Length")
        if isinstance(sl, (int, float)):
            total_m += float(sl)
    return total_m

# ---- DEM slope QA ----

def slope_from_dem_samples(parcel_geom, n_samples=225, slope_units="PERCENT_RISE"):
    xs = [v[0] for r in parcel_geom["rings"] for v in r]
    ys = [v[1] for r in parcel_geom["rings"] for v in r]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    ring = parcel_geom["rings"][0]
    root = max(2, int(n_samples ** 0.5))
    points = []
    for i in range(root):
        for j in range(root):
            x = xmin + (i + 0.5) * (xmax - xmin) / root
            y = ymin + (j + 0.5) * (ymax - ymin) / root
            if point_in_ring(x, y, ring):
                points.append([x, y])
    if not points:
        return {"values": [], "mean": None}

    rendering_rule = {
        "rasterFunction": "Slope",
        "rasterFunctionArguments": {"zFactor": 1, "slopeType": slope_units},
        "variableName": "Raster"
    }
    geom = {"points": points, "spatialReference": {"wkid": SR}}
    js = gpost(DEM_IMAGE + "/getSamples",
               geometryType="esriGeometryMultipoint", geometry=json.dumps(geom),
               inSR=SR, outSR=SR, returnGeometry="false",
               renderingRule=json.dumps(rendering_rule))
    vals = []
    for s in js.get("samples", []):
        try: vals.append(float(s.get("value")))
        except: pass
    if not vals:
        return {"values": [], "mean": None}
    return {"values": vals, "mean": round(sum(vals)/len(vals), 2)}
