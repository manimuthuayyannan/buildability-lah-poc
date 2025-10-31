import argparse, json
from tabulate import tabulate

from .config import (
    FT2_PER_M2,
    ACRES_PER_FT2,
    DEFAULT_CONTOUR_INTERVAL_FT,
)
from .gis import (
    search_parcel_by_address,
    search_parcel_by_apn,
    parcel_area_ft2,
    detect_elev_field,
    contours_inside,
    project_polylines_to_measure,
    length_inside_parcel_ft,
    slope_from_dem_samples,
)
from .lah import (
    average_slope_percent_lah,
    lot_unit_factor,
    mda_mfa_from_luf,
)

def compute_summary(apn, geom, attrs, address=None, skip_dem=True, verbose=False):
    # --- parcel area (ft² & acres) ---
    area_ft2 = parcel_area_ft2(geom)
    area_acres = area_ft2 * ACRES_PER_FT2

    # --- contours inside the parcel ---
    elev_field = detect_elev_field() or "ELEVATION"
    feats = contours_inside(geom, elev_field=elev_field, index_only=False)
    feats_ft = project_polylines_to_measure(feats)
    inside_len_ft_raw, diag = length_inside_parcel_ft(feats_ft, geom, max_seg_len_ft=2.0)

    if inside_len_ft_raw <= 0.0 and verbose:
        print("[CLI] WARNING: zero contour length inside parcel after robust clip.")

    # --- detect which set we actually measured on (5-ft vs 10-ft) ---
    # We treat presence of INTERMEDIATE as "5-ft set available".
    layers = { (f["attributes"].get("LAYER","") or "").upper() for f in feats }
    measured_interval_ft = 5.0 if "INTERMEDIATE" in layers else 10.0

    # --- STEP 1: provisional slope using the measured interval ---
    area_ft2 = parcel_area_ft2(geom)
    area_acres = area_ft2 * ACRES_PER_FT2

    S_prov = average_slope_percent_lah(inside_len_ft_raw, measured_interval_ft, area_acres)

    # --- STEP 2: apply LAH rule for contour interval ---
    # If S_prov <= 10%, LAH requires 2-ft contours.
    # We approximate L at 2-ft by scaling from the measured set.
    interval_used_ft = measured_interval_ft
    inside_len_ft_used = inside_len_ft_raw
    interval_source = "measured"

    if S_prov <= 10.0:
        interval_used_ft = 2.0
        # scale L to equivalent 2-ft length
        # L2 ≈ L_measured * (measured_interval / 2.0)
        scale = measured_interval_ft / 2.0
        inside_len_ft_used = inside_len_ft_raw * scale
        interval_source = f"scaled_from_{int(measured_interval_ft)}ft"

    # --- worksheet math with the final (LAH-compliant) interval ---
    avg_slope = average_slope_percent_lah(inside_len_ft_used, interval_used_ft, area_acres)
    luf = lot_unit_factor(area_acres, avg_slope)
    mda_ft2, mfa_ft2, requires_cdp = mda_mfa_from_luf(avg_slope, luf)

    slope_dem = {"mean": None}
    if not skip_dem:
        slope_dem = slope_from_dem_samples(geom, n_samples=225)

    result = {
        "address": address,
        "apn": apn,
        "parcel_area_ft2": round(area_ft2, 1),
        "parcel_area_acres": round(area_acres, 4),
        "contour_elevation_field": elev_field,
        "contour_count": len(feats),

        # lengths reported both ways for transparency
        "contour_total_length_ft_measured": round(inside_len_ft_raw, 1),
        "contour_total_length_ft": round(inside_len_ft_used, 1),   # the length used for S
        "avg_slope_percent_LAH": round(avg_slope, 1),

        "lot_unit_factor": round(luf, 6),
        "mda_ft2": round(mda_ft2, 1) if mda_ft2 is not None else None,
        "mfa_ft2": round(mfa_ft2, 1) if mfa_ft2 is not None else None,
        "requires_cdp": requires_cdp,
        "slope_percent_dem_QA_mean": slope_dem["mean"],

        "notes": {
            "interval_measured_ft": measured_interval_ft,
            "interval_used_ft": interval_used_ft,
            "interval_source": interval_source,   # "measured" or "scaled_from_5ft/10ft"
            "diagnostics": diag,
        },
    }
    return result

def pretty_print(result):
    rows = [
        ["APN", result["apn"]],
        ["Address", result.get("address") or ""],
        ["Parcel Area (ft²)", f"{result['parcel_area_ft2']:,}"],
        ["Parcel Area (acres)", result["parcel_area_acres"]],
        ["Elevation Field", result["contour_elevation_field"]],
        ["Contour Count", result["contour_count"]],
        ["Total Contour Length (ft)", f"{result['contour_total_length_ft']:,}"],
        ["Average Slope (LAH, %)", result["avg_slope_percent_LAH"]],
        ["Lot Unit Factor (LUF)", result["lot_unit_factor"]],
        ["MDA (ft²)", f"{result['mda_ft2']:,}" if result["mda_ft2"] is not None else "—"],
        ["MFA (ft²)", f"{result['mfa_ft2']:,}" if result["mfa_ft2"] is not None else "—"],
        ["Requires CDP", "Yes" if result["requires_cdp"] else "No"],
        ["DEM Slope QA Mean (%)", result["slope_percent_dem_QA_mean"] if result["slope_percent_dem_QA_mean"] is not None else "—"],
    ]
    print(tabulate(rows, headers=["Metric", "Value"], tablefmt="fancy_grid"))

def run_for_apn(apn, skip_dem=True, verbose=False):
    geom, attrs = search_parcel_by_apn(apn)
    return compute_summary(apn, geom, attrs, skip_dem=skip_dem, verbose=verbose)

def run_for_address(address, skip_dem=True, verbose=False):
    apn, geom, attrs = search_parcel_by_address(address)
    return compute_summary(apn, geom, attrs, address=address, skip_dem=skip_dem, verbose=verbose)

def main():
    p = argparse.ArgumentParser(description="Los Altos Hills Worksheet #1 (S, LUF, MDA, MFA)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--address", help="Street address (e.g., '24785 Prospect Ave, Los Altos Hills, CA')")
    g.add_argument("--apn", help="Assessor Parcel Number (digits only)")
    p.add_argument("--format", choices=["table", "json"], default="table")
    p.add_argument("--skip-dem", action="store_true", help="Skip DEM QA sampling (faster, avoids timeouts)")
    p.add_argument("-v", "--verbose", action="store_true", help="Print extra diagnostics")
    args = p.parse_args()

    try:
        if args.address:
            result = run_for_address(args.address, skip_dem=args.skip_dem, verbose=args.verbose)
        else:
            result = run_for_apn(args.apn, skip_dem=args.skip_dem, verbose=args.verbose)
    except Exception as e:
        print("\n[CLI] FATAL:")
        raise

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        pretty_print(result)

if __name__ == "__main__":
    main()