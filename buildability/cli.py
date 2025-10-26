import argparse, json
from tabulate import tabulate
from .config import FT_PER_M, FT2_PER_M2, ACRES_PER_FT2
from . import config
from .gis import (search_parcel_by_address, search_parcel_by_apn, parcel_area_m2,
                  detect_elev_field, contours_inside, two_ft_subset, contour_length_m,
                  slope_from_dem_samples)
from .lah import (average_slope_percent_lah, lot_unit_factor, mda_mfa_from_luf)

def run_for_apn(apn, contour_interval_ft=2.0):
    geom, attrs = search_parcel_by_apn(apn)
    return compute_summary(apn, geom, attrs, contour_interval_ft)

def run_for_address(address, contour_interval_ft=2.0):
    apn, geom, attrs = search_parcel_by_address(address)
    return compute_summary(apn, geom, attrs, contour_interval_ft, address=address)

def compute_summary(apn, geom, attrs, contour_interval_ft, address=None):
    area_m2 = parcel_area_m2(geom) or float(attrs.get("Shape_Area", 0.0))
    area_ft2 = area_m2 * FT2_PER_M2
    area_acres = area_ft2 * ACRES_PER_FT2

    elev_field = detect_elev_field()
    feats_all = contours_inside(geom, elev_field=elev_field)
    feats_2ft = two_ft_subset(feats_all, elev_field)
    total_len_m = contour_length_m(feats_2ft)
    total_len_ft = total_len_m * FT_PER_M

    avg_slope = average_slope_percent_lah(total_len_ft, contour_interval_ft, area_ft2)
    luf = lot_unit_factor(area_acres, avg_slope)
    mda_ft2, mfa_ft2, requires_cdp = mda_mfa_from_luf(avg_slope, luf)
    slope_dem = slope_from_dem_samples(geom, n_samples=225)

    result = {
        "address": address,
        "apn": apn,
        "parcel_area_ft2": round(area_ft2, 1),
        "parcel_area_acres": round(area_acres, 4),
        "contour_elevation_field": elev_field,
        "contour_2ft_count": len(feats_2ft),
        "contour_2ft_total_length_ft": round(total_len_ft, 1),
        "avg_slope_percent_LAH": avg_slope,
        "lot_unit_factor": luf,
        "mda_ft2": mda_ft2,
        "mfa_ft2": mfa_ft2,
        "requires_cdp": requires_cdp,
        "slope_percent_dem_QA_mean": slope_dem["mean"],
        "notes": {
            "contour_interval_ft": contour_interval_ft,
            "cdp_rule": "If LUF ≤ 0.50, MFA=(LUF/0.50)*5000; MDA=MFA+2100 (SDA may cap additional up to 4500).",
            "disclaimer": "MDA/MFA logic mirrors LAH worksheet; confirm any policy updates with the Town."
        }
    }
    return result

def pretty_print(result):
    rows = [
        ["APN", result["apn"]],
        ["Address", result.get("address") or ""],
        ["Parcel Area (ft²)", f"{result['parcel_area_ft2']:,}"],
        ["Parcel Area (acres)", result["parcel_area_acres"]],
        ["Elevation Field", result["contour_elevation_field"]],
        ["2-ft Contour Count", result["contour_2ft_count"]],
        ["Total Contour Length (ft)", f"{result['contour_2ft_total_length_ft']:,}"],
        ["Average Slope (LAH, %)", result["avg_slope_percent_LAH"]],
        ["Lot Unit Factor (LUF)", result["lot_unit_factor"]],
        ["MDA (ft²)", f"{result['mda_ft2']:,}" if result["mda_ft2"] is not None else None],
        ["MFA (ft²)", f"{result['mfa_ft2']:,}" if result["mfa_ft2"] is not None else None],
        ["Requires CDP", result["requires_cdp"]],
        ["DEM Slope QA Mean (%)", result["slope_percent_dem_QA_mean"]],
    ]
    print(tabulate(rows, headers=["Metric", "Value"], tablefmt="fancy_grid"))

def main():
    p = argparse.ArgumentParser(description="LAH Buildability POC CLI")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--address", help="Street address (e.g., '27181 Adonna Ct, Los Altos Hills, CA')")
    g.add_argument("--apn", help="Assessor Parcel Number (digits only)")
    p.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    p.add_argument("--batch", help="Text file with one address per line (ignores --apn)")
    p.add_argument("--csv", help="Write results to CSV when using --batch")
    p.add_argument("--contour-interval-ft", type=float, default=2.0, help="Contour interval in feet (default 2.0)")
    args = p.parse_args()

    if args.batch:
        import pandas as pd
        rows = []
        with open(args.batch) as f:
            for line in f:
                address = line.strip()
                if not address:
                    continue
                try:
                    res = run_for_address(address, args.contour_interval_ft)
                    rows.append(res)
                    if args.format == "table":
                        pretty_print(res)
                    else:
                        print(json.dumps(res, indent=2))
                except Exception as e:
                    print(f"Error for address '{address}': {e}")
        if args.csv:
            import pandas as pd
            df = pd.DataFrame(rows)
            df.to_csv(args.csv, index=False)
            print(f"✅ Saved {len(rows)} rows to {args.csv}")
        return

    # Single run
    if args.address:
        result = run_for_address(args.address, args.contour_interval_ft)
    else:
        result = run_for_apn(args.apn, args.contour_interval_ft)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        pretty_print(result)

if __name__ == "__main__":
    main()
