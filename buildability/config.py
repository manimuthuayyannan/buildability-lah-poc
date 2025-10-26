FT_PER_M   = 3.28084
FT2_PER_M2 = FT_PER_M**2
ACRES_PER_FT2 = 1.0 / 43560.0

SR = 102100  # Web Mercator

# ArcGIS services
PARCEL_LAYER  = "https://mapservices.sccgov.org/arcgis/rest/services/property/SCCProperty/MapServer/0"
CONTOUR_LAYER = "https://mapservices.sccgov.org/arcgis/rest/services/basic/SCCContour/MapServer/0"
DEM_IMAGE     = "https://mapservices.sccgov.org/arcgis/rest/services/lidar/BareEarth_DEM_HydroFlattened_2020/ImageServer"

HEADERS = {"Referer": "https://geoess.sccgov.org"}

DEFAULT_TIMEOUT = (10, 90)  # (connect, read) seconds – was 30s read before
RETRY_TOTAL = 5
RETRY_BACKOFF = 0.6  # 0.6, 1.2, 2.4, ...
USER_AGENT = "LAH-POC/1.0 (+https://private-open-house)"