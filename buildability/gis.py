import math, time, json, requests
from .config import (
    LAYER_PROPERTY, LAYER_CONTOUR, GEOM_SVC,
    SR_WKID, DEFAULT_TIMEOUT, USER_AGENT,
)
import math

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_base_headers = {"Accept": "application/json"}

def _retry(fn, tries=4, backoff=1.6):
    last = None
    for i in range(tries):
        try:
            return fn()
        except requests.RequestException as e:
            last = e
            if i == tries-1: raise
            time.sleep(backoff*(i+1))
    raise last

def _t_get(url, params):
    params = {"f":"json", **params}
    r = _retry(lambda: _session.get(url, params=params, headers=_base_headers, timeout=DEFAULT_TIMEOUT))
    r.raise_for_status()
    js = r.json()
    if "error" in js: raise RuntimeError(js["error"])
    return js

def _t_post(url, data):
    data = {"f":"json", **data}
    r = _retry(lambda: _session.post(url, data=data, headers=_base_headers, timeout=DEFAULT_TIMEOUT))
    r.raise_for_status()
    js = r.json()
    if "error" in js: raise RuntimeError(js["error"])
    return js

def _densify_polylines_local(geoms, max_seg_len_ft=2.0):
    """Split every segment so no piece exceeds max_seg_len_ft."""
    out = []
    for g in geoms:
        new_paths = []
        for path in g.get("paths", []):
            if not path: 
                continue
            acc = [path[0]]
            for i in range(len(path)-1):
                x1,y1 = path[i]
                x2,y2 = path[i+1]
                dx, dy = x2-x1, y2-y1
                seg_len = math.hypot(dx, dy)
                if seg_len <= max_seg_len_ft or seg_len == 0.0:
                    acc.append([x2,y2])
                else:
                    n = max(1, int(math.ceil(seg_len / max_seg_len_ft)))
                    for k in range(1, n+1):
                        t = k / n
                        acc.append([x1 + dx*t, y1 + dy*t])
            new_paths.append(acc)
        out.append({"paths": new_paths})
    return out

def _point_on_segment_eps(px, py, x1, y1, x2, y2, eps=0.5):
    """Distance from point to segment <= eps? (treat boundary as inside)."""
    vx, vy = x2-x1, y2-y1
    wx, wy = px-x1, py-y1
    seg_len2 = vx*vx + vy*vy
    if seg_len2 == 0.0:
        # degenerate segment
        return math.hypot(px-x1, py-y1) <= eps
    t = max(0.0, min(1.0, (wx*vx + wy*vy)/seg_len2))
    cx, cy = x1 + t*vx, y1 + t*vy
    return math.hypot(px-cx, py-cy) <= eps

def _point_in_polygon_with_tol(px, py, rings, eps=0.5):
    """Ray-cast with edge tolerance: points on/within eps of any edge are 'inside'."""
    # Edge tolerance
    for ring in rings:
        for i in range(len(ring)-1):
            x1,y1 = ring[i]; x2,y2 = ring[i+1]
            if _point_on_segment_eps(px, py, x1, y1, x2, y2, eps=eps):
                return True

    # Standard even-odd rule
    inside = False
    for ring in rings:
        for i in range(len(ring)-1):
            x1,y1 = ring[i]; x2,y2 = ring[i+1]
            if ((y1 > py) != (y2 > py)):
                xint = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
                if xint >= px:
                    inside = not inside
    return inside

def _polyline_length_inside_polygon_local(geoms, parcel_geom, eps=0.5):
    """Sum of segment lengths whose midpoints are inside parcel (with edge tol)."""
    rings = parcel_geom.get("rings", [])
    total = 0.0
    for g in geoms:
        for path in g.get("paths", []):
            for i in range(len(path)-1):
                x1,y1 = path[i]; x2,y2 = path[i+1]
                mx, my = (x1+x2)/2.0, (y1+y2)/2.0
                if _point_in_polygon_with_tol(mx, my, rings, eps=eps):
                    total += math.hypot(x2-x1, y2-y1)
    return total

def _polyline_length_ft(geoms):
    total = 0.0
    for g in geoms:
        for path in g.get("paths", []):
            for i in range(len(path)-1):
                x1,y1 = path[i]; x2,y2 = path[i+1]
                total += math.hypot(x2-x1, y2-y1)
    return total
# -----------------------------
# Parcel lookups
# -----------------------------
def search_parcel_by_address(address: str):
    # Expect "24785 Prospect Ave, Los Altos Hills, CA"
    parts = address.strip().split(" ", 1)
    if len(parts) < 2:
        raise RuntimeError("Address must start with house number and street")
    house = parts[0]
    street_full = parts[1].split(",")[0].strip()
    street_head = street_full.split()[0].upper()

    where = f"SITUS_HOUSE_NUMBER LIKE '{house}%' AND SITUS_STREET_NAME LIKE '{street_head}%'"
    js = _t_post(f"{LAYER_PROPERTY}/query", {
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": SR_WKID,
        "resultRecordCount": 5
    })
    feats = js.get("features", [])
    if not feats:
        raise RuntimeError("Parcel not found for address")
    f = feats[0]
    apn = f["attributes"]["APN"]
    return apn, f["geometry"], f["attributes"]

def search_parcel_by_apn(apn: str):
    js = _t_post(f"{LAYER_PROPERTY}/query", {
        "where": f"APN='{apn}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": SR_WKID
    })
    feats = js.get("features", [])
    if not feats:
        raise RuntimeError("Parcel not found for APN")
    f = feats[0]
    return f["geometry"], f["attributes"]

# -----------------------------
# Area helpers
# -----------------------------
def parcel_area_ft2(geom):
    # Prefer server areasAndLengths (feet). Fall back to planar ring area in feet.
    try:
        js = _t_post(f"{GEOM_SVC}/areasAndLengths", {
            "sr": json.dumps({"wkid": SR_WKID}),
            "polygons": json.dumps([geom]),
            "lengthUnit": 9002,  # foot
            "areaUnit": {"areaUnit":"esriSquareFeet"}
        })
        return float(js["areas"][0])
    except Exception as e:
        print(f"[GIS] areasAndLengths failed, falling back to local area: {e}")
        return _planar_area_ft2(geom)

def _planar_area_ft2(geom):
    def ring_area(ring):
        a = 0.0
        for i in range(len(ring)-1):
            x1,y1 = ring[i]; x2,y2 = ring[i+1]
            a += x1*y2 - x2*y1
        return abs(a/2.0)
    area = 0.0
    for ring in geom.get("rings", []):
        area += ring_area(ring)
    return area

# -----------------------------
# Contours & length inside parcel
# -----------------------------
def detect_elev_field():
    # LA County layer uses ELEVATION; keep hook if ever needed
    return "ELEVATION"

def _query_contours(parcel_geom):
    where = "ELEVATION IS NOT NULL AND (UPPER(LAYER)='INDEX' OR UPPER(LAYER)='INTERMEDIATE')"
    js = _t_post(f"{LAYER_CONTOUR}/query", {
        "where": where,
        "outFields": "OBJECTID,ELEVATION,LAYER",
        "returnGeometry": "true",
        "geometry": json.dumps(parcel_geom),
        "geometryType": "esriGeometryPolygon",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": SR_WKID,
        "outSR": SR_WKID,
        "geometryPrecision": 2,
        "maxAllowableOffset": 0.5,
        "resultRecordCount": 5000
    })
    feats = js.get("features", [])
    print(f"[GIS] Contours fetched (filtered): {len(feats)}")
    return feats

def _intersect_length_ft(lines_geoms, parcel_geom):
    # Intersect: send polylines as "geometries", parcel as "geometry"
    js = _t_post(f"{GEOM_SVC}/intersect", {
        "sr": json.dumps({"wkid": SR_WKID}),
        "geometries": json.dumps({"geometryType":"esriGeometryPolyline", "geometries": lines_geoms}),
        "geometry": json.dumps(parcel_geom),
        "geometryType": "esriGeometryPolygon"
    })
    geoms = js.get("geometries", [])
    return _polyline_length_ft(geoms)

def _polyline_length_ft(geoms):
    def path_len(path):
        tot = 0.0
        for i in range(len(path)-1):
            x1,y1 = path[i]; x2,y2 = path[i+1]
            tot += math.hypot(x2-x1, y2-y1)
        return tot
    total = 0.0
    for g in geoms:
        for p in g.get("paths", []):
            total += path_len(p)
    return total

def contours_inside(parcel_geom, elev_field="ELEVATION", index_only=False):
    feats = _query_contours(parcel_geom)
    if index_only:
        feats = [f for f in feats if str(f["attributes"].get("LAYER","")).upper()=="INDEX"]
    return feats

def project_polylines_to_measure(feats):
    # Input already requested in SR_WKID; just return geometry objects (polylines)
    return [f["geometry"] for f in feats]

def length_inside_parcel_ft(contour_geoms_ft, parcel_geom, max_seg_len_ft=2.0):
    """
    Local, serverless computation:
    1) densify all contour paths to <= max_seg_len_ft
    2) count the length of segments whose midpoints are inside the parcel
       (boundary within eps=0.5 ft is treated as inside, matching worksheet behavior)
    """
    # Local densify (no GeometryServer calls)
    dens = _densify_polylines_local(contour_geoms_ft, max_seg_len_ft=max_seg_len_ft)

    # Measure length of densified segments inside polygon with edge tolerance
    inside_len = _polyline_length_inside_polygon_local(dens, parcel_geom, eps=0.5)

    # If still zero, relax tolerance slightly as a last resort
    if inside_len == 0.0:
        inside_len = _polyline_length_inside_polygon_local(dens, parcel_geom, eps=1.0)

    return round(inside_len, 2), {"method": "local_densify+midpoint_with_edge_tolerance"}

def slope_from_dem_samples(*args, **kwargs):
    # Keep stub for CLI flag parity; DEM QA is optional and flaky on slow server
    return {"mean": None}