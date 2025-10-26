# Buildability LAH POC

End-to-end, runnable Proof of Concept to compute **Average Slope (LAH official)**,
**Lot Unit Factor (LUF)**, **MDA**, and **MFA** from Santa Clara County ArcGIS services.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Single address, pretty table output
python -m buildability.cli --address "27181 Adonna Ct, Los Altos Hills, CA"

# JSON output
python -m buildability.cli --address "27181 Adonna Ct, Los Altos Hills, CA" --format json

# APN instead of address
python -m buildability.cli --apn 18204019

# Batch addresses from a text file (one per line) to CSV
python -m buildability.cli --batch addresses.txt --csv results.csv
```

## Files

- `buildability/gis.py` — ArcGIS REST helpers (parcel lookup, contours, DEM slope QA)
- `buildability/lah.py` — Official LAH formulas (Average Slope, LUF, MDA, MFA)
- `buildability/config.py` — Service URLs, constants
- `buildability/cli.py` — Command-line interface (address or APN input)
- `requirements.txt` — dependencies
