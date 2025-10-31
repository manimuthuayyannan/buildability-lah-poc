# streamlit_app.py
import io
import json
import math
import time
import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Page config MUST be the first Streamlit call on the page
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Los Altos Hills Buildability Calculator", layout="wide")

from buildability.gis import (
    search_parcel_by_address,
    search_parcel_by_apn,
    parcel_area_ft2,
    detect_elev_field,
    contours_inside,
    project_polylines_to_measure,
    length_inside_parcel_ft,
)
from buildability.lah import (
    average_slope_percent_lah,
    lot_unit_factor,
    mda_mfa_from_luf,
)
from buildability.config import ACRES_PER_FT2

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
    try:
        return _run_for_address(address, interval_ft, skip_dem)
    except TypeError:
        pass
    try:
        return _run_for_address(address, interval_ft)
    except TypeError:
        pass
    try:
        return _run_for_address(address, skip_dem)
    except TypeError:
        pass
    try:
        return _run_for_address(address, contour_interval_ft=interval_ft, skip_dem=skip_dem)
    except TypeError:
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
    if x is None:
        return "—"
    try:
        xf = float(x)
    except Exception:
        return str(x)
    if math.isnan(xf) or math.isinf(xf):
        return "—"
    return f"{round(xf, places):,.{places}f}"

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
        "dem_slope_qa_mean": (
            res.get("slope_percent_dem_QA_mean")
            if isinstance(res.get("slope_percent_dem_QA_mean"), (int, float))
            else None
        ),
        "notes_contour_interval_selected_ft": res.get("notes", {}).get("contour_interval_ft_selected"),
        "notes_contour_interval_used_ft": res.get("notes", {}).get("contour_interval_ft_used"),
    }

def show_result_cards(res: dict):
    slope = float(res.get("avg_slope_percent_LAH", 0.0) or 0.0)
    luf   = float(res.get("lot_unit_factor", 0.0) or 0.0)
    mda   = float(res.get("mda_ft2", 0.0) or 0.0)
    mfa   = float(res.get("mfa_ft2", 0.0) or 0.0)

    slope_cls = "green" if slope <= 10 else ("orange" if slope <= 20 else "red")

    c1, c2, c3, c4 = st.columns(4)

    # Average Slope
    c1.markdown(
        _metric_card_html("Average Slope (LAH)", f"{slope:,.1f}%"),  # color via container
        unsafe_allow_html=True
    )
    # LUF
    c2.markdown(
        _metric_card_html("Lot Unit Factor (LUF)", f"{luf:.6f}"),
        unsafe_allow_html=True
    )
    # MDA
    c3.markdown(
        _metric_card_html("Maximum Development Area (MDA)", f"{mda:,.1f} ft²"),
        unsafe_allow_html=True
    )
    # MFA
    c4.markdown(
        _metric_card_html("Maximum Floor Area (MFA)", f"{mfa:,.1f} ft²"),
        unsafe_allow_html=True
    )

def show_detail_table(res: dict):
    rows = [
        ("APN", res.get("apn")),
        ("Parcel Area (ft²)", _fmt_num(res.get("parcel_area_ft2"), 1)),
        ("Parcel Area (acres)", _fmt_num(res.get("parcel_area_acres"), 4)),
        ("Elevation Field", res.get("contour_elevation_field")),
        ("Contour Count", res.get("contour_count")),
        ("Total Contour Length (measured, ft)", _fmt_num(res.get("contour_total_length_ft_measured"), 1)),
        ("Total Contour Length (used, ft)", _fmt_num(res.get("contour_total_length_ft"), 1)),
        ("Average Slope (LAH, %)", _fmt_num(res.get("avg_slope_percent_LAH", 0.0), 1)),
        ("Lot Unit Factor (LUF)", _fmt_num(res.get("lot_unit_factor"), 6)),
        ("MDA (ft²)", _fmt_num(res.get("mda_ft2"), 1)),
        ("MFA (ft²)", _fmt_num(res.get("mfa_ft2"), 1)),
        ("Requires CDP", "Yes" if res.get("requires_cdp") else "No"),
        ("Interval (measured, ft)", res.get("notes",{}).get("interval_measured_ft")),
        ("Interval (used for LAH, ft)", res.get("notes",{}).get("interval_used_ft")),
        ("Interval source", res.get("notes",{}).get("interval_source")),
    ]
    df = pd.DataFrame(rows, columns=["Metric", "Value"])
    # ensure Arrow-friendly types
    df["Value"] = df["Value"].astype(str)
    st.table(df)

def make_json_download(res: dict) -> bytes:
    return json.dumps(res, indent=2, ensure_ascii=False).encode("utf-8")

def make_csv_download(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

# ──────────────────────────────────────────────────────────────────────────────
# Global styles (after page config)
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card{background:#fff;border-radius:16px;padding:20px;
box-shadow:0 2px 8px rgba(0,0,0,.05);text-align:center;border-top:4px solid #004C97}
.metric-card h4{margin:0 0 6px 0;font-weight:600;color:#004C97}
.metric-card .val{margin:0;font-size:2.4rem;font-weight:800;color:#004C97}
</style>
""", unsafe_allow_html=True)

def _metric_card_html(title:str, value_html:str):
    return f'''
    <div class="metric-card">
      <h4>{title}</h4>
      <div class="val">{value_html}</div>
    </div>
    '''

# ------------- UI -------------
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
        prog = st.progress(0)
        step = st.empty()
        try:
            t0 = time.time()
            if mode == "Address":
                addr = address.strip()
                step.info("🔎 Looking up parcel…")
                apn, geom, attrs = search_parcel_by_address(addr)
            else:
                apn_val = apn.strip()
                step.info("🔎 Looking up parcel by APN…")
                geom, attrs = search_parcel_by_apn(apn_val)
                addr = None
                apn = apn_val
            prog.progress(0.15)

            # Area
            step.info("📐 Calculating parcel area…")
            area_ft2 = parcel_area_ft2(geom)
            area_acres = area_ft2 * ACRES_PER_FT2
            prog.progress(0.30)

            # Contours
            step.info("🗺️ Fetching parcel contours…")
            elev_field = detect_elev_field() or "ELEVATION"
            feats = contours_inside(geom, elev_field=elev_field, index_only=False)
            feats_ft = project_polylines_to_measure(feats)
            prog.progress(0.50)

            # Length inside parcel (robust)
            step.info("📏 Measuring contour length inside parcel…")
            inside_len_ft_raw, diag = length_inside_parcel_ft(feats_ft, geom, max_seg_len_ft=2.0)
            if inside_len_ft_raw <= 0.0:
                st.warning("Zero contour length detected inside parcel (rare edge/topology case).")
            prog.progress(0.65)

            # Determine measured interval (5-ft if INTERMEDIATE present, else 10-ft)
            layers = {(f["attributes"].get("LAYER","") or "").upper() for f in feats}
            measured_interval_ft = 5.0 if "INTERMEDIATE" in layers else 10.0

            # Provisional slope with measured interval
            step.info("⚖️ Applying LAH interval rule & worksheet math…")
            S_prov = average_slope_percent_lah(inside_len_ft_raw, measured_interval_ft, area_acres)

            # LAH: if slope ≤ 10%, use 2-ft interval (scale L to 2-ft)
            interval_used_ft = measured_interval_ft
            inside_len_ft_used = inside_len_ft_raw
            interval_source = "measured"
            if S_prov <= 10.0:
                interval_used_ft = 2.0
                inside_len_ft_used = inside_len_ft_raw * (measured_interval_ft / 2.0)
                interval_source = f"scaled_from_{int(measured_interval_ft)}ft"

            # Final worksheet metrics
            avg_slope = average_slope_percent_lah(inside_len_ft_used, interval_used_ft, area_acres)
            luf = lot_unit_factor(area_acres, avg_slope)
            mda_ft2, mfa_ft2, requires_cdp = mda_mfa_from_luf(avg_slope, luf)
            prog.progress(0.85)

            # Assemble result like CLI
            res = {
                "address": addr,
                "apn": apn,
                "parcel_area_ft2": round(area_ft2, 1),
                "parcel_area_acres": round(area_acres, 4),
                "contour_elevation_field": elev_field,
                "contour_count": len(feats),
                "contour_total_length_ft_measured": round(inside_len_ft_raw, 1),
                "contour_total_length_ft": round(inside_len_ft_used, 1),
                "avg_slope_percent_LAH": round(avg_slope, 1),
                "lot_unit_factor": round(luf, 6),
                "mda_ft2": round(mda_ft2, 1),
                "mfa_ft2": round(mfa_ft2, 1),
                "requires_cdp": requires_cdp,
                "slope_percent_dem_QA_mean": None,
                "notes": {
                    "interval_measured_ft": measured_interval_ft,
                    "interval_used_ft": interval_used_ft,
                    "interval_source": interval_source,
                    "diagnostics": diag,
                },
            }
            t1 = time.time()
            prog.progress(1.0)
            step.success("✅ Analysis completed.")

            # Render UI
            show_result_cards(res)
            with st.expander("Detailed Results", expanded=True):
                show_detail_table(res)

            colj, colc = st.columns(2)
            colj.download_button("⬇️ Download JSON", data=make_json_download(res),
                                 file_name="lah_buildability.json", mime="application/json")
            df_single = pd.DataFrame([result_to_row(res)])
            colc.download_button("⬇️ Download CSV", data=make_csv_download(df_single),
                                 file_name="lah_buildability.csv", mime="text/csv")

            st.caption(
                f"Notes • Interval measured: {measured_interval_ft:.0f} ft • "
                f"Interval used (LAH): {interval_used_ft:.0f} ft ({interval_source}) • "
                f"Runtime: {(t1 - t0):.2f}s"
            )
            st.caption("CDP rule: If LUF ≤ 0.50, MFA=(LUF/0.50)*5000; MDA=MFA+2100 (SDA may cap additional up to 4500).")
            st.caption("Disclaimer: MDA/MFA logic mirrors LAH worksheet; confirm any policy updates with the Town.")

        except Exception as e:
            prog.progress(0.0)
            step.error("❌ Analysis failed.")
            st.error(f"{e}")

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