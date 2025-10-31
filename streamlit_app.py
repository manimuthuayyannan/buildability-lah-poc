# streamlit_app.py
import io
import json
import math
import time
import pandas as pd
import streamlit as st

# --- Pull core functions from your package ---
try:
    # Preferred: import from your CLI module (where you defined them)
    from buildability.cli import run_for_address as _run_for_address, run_for_apn as _run_for_apn
except Exception:
    # Fallback if you moved these into another module later
    from buildability import run_for_address as _run_for_address, run_for_apn as _run_for_apn  # type: ignore

try:
    from buildability.config import DEFAULT_CONTOUR_INTERVAL_FT
except Exception:
    DEFAULT_CONTOUR_INTERVAL_FT = 2.0  # safe default

# ------------- Compatibility shims (handle different function signatures) -------------
def call_run_for_address(address: str, interval_ft: float, skip_dem: bool):
    """
    Tries common signatures in order so the app stays compatible with your evolving CLI.
    """
    # Try: (address, interval, skip_dem)
    try:
        return _run_for_address(address, interval_ft, skip_dem)
    except TypeError:
        pass
    # Try: (address, interval)
    try:
        return _run_for_address(address, interval_ft)
    except TypeError:
        pass
    # Try: (address, skip_dem)
    try:
        return _run_for_address(address, skip_dem)
    except TypeError:
        pass
    # Try keyword only
    try:
        return _run_for_address(address, contour_interval_ft=interval_ft, skip_dem=skip_dem)
    except TypeError:
        # Last resort: only the address
        return _run_for_address(address)

def call_run_for_apn(apn: str, interval_ft: float, skip_dem: bool):
    try:
        return _run_for_apn(apn, interval_ft, skip_dem)
    except TypeError:
        pass
    try:
        return _run_for_apn(apn, interval_ft)
    except TypeError:
        pass
    try:
        return _run_for_apn(apn, skip_dem)
    except TypeError:
        pass
    try:
        return _run_for_apn(apn, contour_interval_ft=interval_ft, skip_dem=skip_dem)
    except TypeError:
        return _run_for_apn(apn)

# ------------- Small helpers -------------
def _fmt_num(x, places=1):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{round(float(x), places):,.{places}f}"

def result_to_row(res: dict) -> dict:
    """Normalize keys for dataframe/export."""
    return {
        "apn": res.get("apn"),
        "address": res.get("address"),
        "parcel_area_ft2": res.get("parcel_area_ft2"),
        "parcel_area_acres": res.get("parcel_area_acres"),
        "elevation_field": res.get("contour_elevation_field"),
        "contour_count": res.get("contour_count"),
        "contour_total_length_ft": res.get("contour_total_length_ft"),
        "avg_slope_percent_LAH": res.get("avg_slope_percent_LAH", 0.0),
        "lot_unit_factor": res.get("lot_unit_factor"),
        "mda_ft2": res.get("mda_ft2"),
        "mfa_ft2": res.get("mfa_ft2"),
        "requires_cdp": res.get("requires_cdp"),
        "dem_slope_qa_mean": (res.get("slope_percent_dem_QA_mean") if isinstance(res.get("slope_percent_dem_QA_mean"), (int,float)) else None),
        "notes_contour_interval_selected_ft": res.get("notes", {}).get("contour_interval_ft_selected"),
        "notes_contour_interval_used_ft": res.get("notes", {}).get("contour_interval_ft_used"),
    }

def show_result_cards(res: dict):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Slope (LAH)", f"{_fmt_num(res.get('avg_slope_percent_LAH', 0.0), 1)}%")
    c2.metric("Lot Unit Factor", _fmt_num(res.get("lot_unit_factor"), 6))
    c3.metric("MDA", f"{_fmt_num(res.get('mda_ft2'), 1)} ft²")
    c4.metric("MFA", f"{_fmt_num(res.get('mfa_ft2'), 1)} ft²")

def show_detail_table(res: dict):
    rows = [
        ("APN", res.get("apn")),
        ("Parcel Area (ft²)", _fmt_num(res.get("parcel_area_ft2"), 1)),
        ("Parcel Area (acres)", _fmt_num(res.get("parcel_area_acres"), 4)),
        ("Elevation Field", res.get("contour_elevation_field")),
        ("2-ft Contour Count", res.get("contour_count")),
        ("Total Contour Length (ft)", _fmt_num(res.get("contour_total_length_ft"), 1)),
        ("Average Slope (LAH, %)", _fmt_num(res.get("avg_slope_percent_LAH", 0.0), 1)),
        ("Lot Unit Factor (LUF)", _fmt_num(res.get("lot_unit_factor"), 6)),
        ("MDA (ft²)", _fmt_num(res.get("mda_ft2"), 1)),
        ("MFA (ft²)", _fmt_num(res.get("mfa_ft2"), 1)),
        ("Requires CDP", "Yes" if res.get("requires_cdp") else "No"),
        ("DEM Slope QA Mean (%)", _fmt_num(res.get("slope_percent_dem_QA_mean"), 2) if res.get("slope_percent_dem_QA_mean") is not None else "—"),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    st.table(df)

def make_json_download(res: dict) -> bytes:
    return json.dumps(res, indent=2, ensure_ascii=False).encode("utf-8")

def make_csv_download(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

# ------------- UI -------------
st.set_page_config(page_title="Los Altos Hills Buildability Calculator", layout="wide")
st.title("🏗️ Los Altos Hills Buildability Calculator")

with st.sidebar:
    st.caption("Compute Average Slope, LUF, MDA, MFA using live Santa Clara County GIS (via your package).")

    mode = st.radio("Lookup by", options=["Address", "APN"], horizontal=True)
    interval = st.slider("Contour interval (ft)", min_value=1.0, max_value=10.0, value=float(DEFAULT_CONTOUR_INTERVAL_FT), step=1.0)
    skip_dem = st.checkbox("Skip DEM QA (faster)", value=True,
                           help="If county services are slow, keep DEM skipped for speed.")

    tabs = st.radio("Mode", options=["Single Parcel", "Batch Mode"], horizontal=True)

# -------- Single Parcel --------
if tabs == "Single Parcel":
    if mode == "Address":
        address = st.text_input("Address", value="27181 Adonna Ct, Los Altos Hills, CA")
    else:
        apn = st.text_input("APN", value="", placeholder="e.g., 33628010")

    run = st.button("Analyze", type="primary")
    if run:
        try:
            t0 = time.time()
            if mode == "Address":
                res = call_run_for_address(address.strip(), interval, skip_dem)
            else:
                res = call_run_for_apn(apn.strip(), interval, skip_dem)
            t1 = time.time()

            st.success("Analysis completed successfully.")
            show_result_cards(res)

            with st.expander("Detailed Results", expanded=True):
                show_detail_table(res)

            colj, colc = st.columns(2)
            colj.download_button("⬇️ Download JSON", data=make_json_download(res),
                                 file_name="lah_buildability.json", mime="application/json")
            df_single = pd.DataFrame([result_to_row(res)])
            colc.download_button("⬇️ Download CSV", data=make_csv_download(df_single),
                                 file_name="lah_buildability.csv", mime="text/csv")

            st.caption(f"Notes • Contour interval: {interval:.1f} ft • Runtime: {(t1 - t0):.2f}s")
            st.caption("CDP rule: If LUF ≤ 0.50, MFA=(LUF/0.50)*5000; MDA=MFA+2100 (SDA may cap additional up to 4500).")
            st.caption("Disclaimer: MDA/MFA logic mirrors LAH worksheet; confirm any policy updates with the Town.")

        except Exception as e:
            st.error(f"Analysis failed: {e}")

# -------- Batch Mode --------
else:
    st.write("Upload a CSV with either a column **address** or **apn** (or both).")
    tmpl = pd.DataFrame({"address": ["27181 Adonna Ct, Los Altos Hills, CA"], "apn": [""]})
    st.download_button("⬇️ Template CSV", make_csv_download(tmpl), "template.csv", "text/csv")

    up = st.file_uploader("CSV file", type=["csv"])
    batch_skip_dem = st.checkbox("Skip DEM QA for batch (recommended)", value=True)
    go = st.button("Run Batch", type="primary", disabled=up is None)

    if go and up is not None:
        try:
            src = pd.read_csv(up).fillna("")
            if not ({"address", "apn"} & set(src.columns)):
                st.error("CSV must include at least one of: 'address' or 'apn'.")
            else:
                out_rows = []
                prog = st.progress(0.0)
                for i, row in src.iterrows():
                    try:
                        if str(row.get("address", "")).strip():
                            res = call_run_for_address(str(row["address"]).strip(), interval, batch_skip_dem)
                        else:
                            res = call_run_for_apn(str(row["apn"]).strip(), interval, batch_skip_dem)
                        out_rows.append(result_to_row(res))
                    except Exception as ex:
                        out_rows.append({"address": row.get("address", ""), "apn": row.get("apn", ""), "error": str(ex)})
                    prog.progress((i + 1) / len(src))
                prog.empty()

                out_df = pd.DataFrame(out_rows)
                st.success(f"Completed {len(out_df)} rows.")
                st.dataframe(out_df, use_container_width=True, height=400)

                c1, c2 = st.columns(2)
                c1.download_button("⬇️ Download CSV", data=make_csv_download(out_df),
                                   file_name="lah_buildability_batch.csv", mime="text/csv")
                c2.download_button("⬇️ Download JSON", data=json.dumps(out_rows, indent=2).encode("utf-8"),
                                   file_name="lah_buildability_batch.json", mime="application/json")

                st.caption("Tip: If county GIS is slow or rate-limited, keep DEM skipped and stagger runs.")
        except Exception as e:
            st.error(f"Batch failed: {e}")