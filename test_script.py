from buildability.gis import gpost, gget, GEOM_SVC, SR, SR_MEASURE, CONTOUR_LAYER
import json

# 1️⃣ Query the parcel geometry by APN
parcel = gget(
    "https://mapservices.sccgov.org/arcgis/rest/services/property/SCCProperty/MapServer/0/query",
    where="APN='33628010'",
    outFields="*",
    returnGeometry="true",
    outSR=SR,
)
geom = parcel["features"][0]["geometry"]

# 2️⃣ Project to SR_MEASURE (ft) with tolerance
proj = gpost(
    f"{GEOM_SVC}/project",
    inSR=SR,
    outSR=SR_MEASURE,
    geometries=json.dumps({
        "geometryType": "esriGeometryPolygon",
        "geometries": [geom],
    }),
)
parcel_proj = proj["geometries"][0]

# 3️⃣ Query contours — with precision safety
where = "ELEVATION IS NOT NULL"
result = gget(
    CONTOUR_LAYER + "/query",
    where=where,
    outFields="ELEVATION,LAYER",
    returnGeometry="false",
    geometry=json.dumps(parcel_proj),
    geometryType="esriGeometryPolygon",
    spatialRel="esriSpatialRelIntersects",
    inSR=SR_MEASURE,
    outSR=SR_MEASURE,
    geometryPrecision=2,          # 🧩 prevent rounding mismatch
    maxAllowableOffset=0.5,       # 🧩 help with small parcels
    resultRecordCount=5000,
)

print(f"Contours found: {len(result.get('features', []))}")
if result.get("features"):
    print("Sample elevations:", [f["attributes"]["ELEVATION"] for f in result["features"][:5]])
    