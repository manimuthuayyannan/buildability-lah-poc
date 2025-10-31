# Units
FT2_PER_M2 = 10.763910416709722
ACRES_PER_FT2 = 1.0 / 43560.0

# Default interval shown in CLI help (the code auto-detects 5 vs 10 from LAYER)
DEFAULT_CONTOUR_INTERVAL_FT = 5.0  # informational; actual value is picked from LAYER

# Services (Santa Clara County)
SCC_BASE = "https://mapservices.sccgov.org/arcgis/rest/services"
LAYER_PROPERTY = f"{SCC_BASE}/property/SCCProperty/MapServer/0"
LAYER_CONTOUR  = f"{SCC_BASE}/basic/SCCContour/MapServer/0"
GEOM_SVC       = f"{SCC_BASE}/Utilities/Geometry/GeometryServer"

# Spatial reference — feet
SR_WKID = 2227  # NAD83 / California zone III (ftUS)

# HTTP
DEFAULT_TIMEOUT = 40  # seconds
USER_AGENT = "buildability-lah/1.0"