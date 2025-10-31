# app.py
import os, sys, json, math
import pandas as pd
import streamlit as st
import requests
import time

# Ensure local package imports work when launched via `streamlit run app.py`
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from buildability.cli import run_for_address, run_for_apn  # core logic


# ------------------------ Page & Theme ------------------------
st.set_page_config(
    page_title="LAH Buildability Analyzer",
    page_icon="🏡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ------------------------ Styling ------------------------
st.markdown("""
<style>
.block-container {max-width: 980px;}
.glass {
  background: linear-gradient(180deg, rgba(255,255,255,.75), rgba(255,255,255,.45));
  backdrop-filter: blur(6px);
  border: 1px solid rgba(200,200,200,.4);
  border-radius: 18px;
  padding: 18px 22px;
  box-shadow: 0 10px 30px rgba(0,0,0,.05);
}
.card {
  border-radius: 16px;
  padding: 16px 16px;
  border: 1px solid rgba(210,210,210,.45);
  background: linear-gradient(180deg, rgba(255,255,255,.9), rgba(245,247,250,.9));
}
.card h3 {
  margin: 0; font-size: 13px; font-weight: 600; color: #506174; letter-spacing: .2px;
}
.card p {
  margin: 2px 0 0; font-size: 26px; font-weight: 700; color: #0f172a;
}
.badge {
  display:inline-block; padding: 4px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; border:1px solid rgba(0,0,0,.08);
}
.badge.ok { color:#0a7f22; background:rgba(10,127,34,.08); }
.badge.warn { color:#a10; background:rgba(170,16,0,.08); }
.table {
  width:100%; border-collapse: collapse; border-radius:16px; overflow:hidden;
  border:1px solid rgba(210,210,210,.45);
}
.table th, .table td {
  text-align:left; padding:10px 12px; border-bottom:1px solid #f0f2f5; font-size:14px;
}
.table thead th { background:#f6f8fb; color:#475569; font-weight:700; }
.table tr:last-child td { border-bottom:none; }
.note { color:#475569; font-size:13px; }
.small { color:#64748b; font-size:12px; }
.kv { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size:12px; color:#334155;}
</style>
""", unsafe_allow_html=True)

# ------------------------ Header ------------------------
with st.container():
    st.markdown("""
    <div class="glass">
        <h1 style="margin:0 0 6px 0">🏡 Los Altos Hills Buildability Analyzer</h1>
        <div class="small">Compute <b>Average Slope</b>, <b>LUF</b>, <b>MDA</b>, and <b>MFA</b> using live Santa Clara County GIS.</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ------------------------ Controls ------------------------
colA, colB = st.columns([1, 2])
with colA:
    mode = st.radio("Search by", ["Address", "APN"], horizontal=True, label_visibility="collapsed")
with colB:
    placeholder = "24785 Prospect Ave, Los Altos Hills, CA" if mode == "Address" else "18204019"
    user_input = st.text_input("Input", placeholder, label_visibility="collapsed")

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    ci = st.select_slider("Contour interval (ft)", options=[1.0, 2.0, 5.0, 10.0], value=2.0,
                          help="LAH worksheet uses 2-ft contours by default. Change only for testing.")
with c2:
    qa_samples = st.select_slider("DEM samples (QA only)", options=[64, 100, 144, 196, 225, 400], value=64,
                                  help="Affects only DEM slope QA; smaller is faster.")
with c3:
    run_btn = st.button("Analyze", type="primary", use_container_width=True)

show_diag = st.toggle("Show diagnostics", value=False, help="Reveal raw data, intervals, and field mappings.")

# ------------------------ Helpers ------------------------
def fmt_num(x, decimals=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    if isinstance(x, (int, float)):
        return f"{x:,.{decimals}f}" if decimals is not None else f"{x:,}"
    return str(x)

def build_rows(result: dict):
    return [
        ("APN",                        str(result["apn"])),
        ("Parcel Area (ft²)",          fmt_num(result["parcel_area_ft2"], 1)),
        ("Parcel Area (acres)",        fmt_num(result["parcel_area_acres"], 4)),
        ("Elevation Field",            str(result["contour_elevation_field"])),
        ("Contour Count",              fmt_num(result["contour_count"], None)),
        ("Total Contour Length (ft)",  fmt_num(result["contour_total_length_ft"], 1)),
        ("Average Slope (LAH, %)",     fmt_num(result["avg_slope_percent_LAH"], 2)),
        ("Lot Unit Factor (LUF)",      fmt_num(result["lot_unit_factor"], 6)),
        ("MDA (ft²)",                  fmt_num(result["mda_ft2"], 1)),
        ("MFA (ft²)",                  fmt_num(result["mfa_ft2"], 1)),
        ("Requires CDP",               "Yes" if result["requires_cdp"] else "No"),
        ("DEM Slope QA Mean (%)",      fmt_num(result["slope_percent_dem_QA_mean"], 2)),
    ]

def render_detail_table(rows):
    html = ["<table class='table'><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"]
    for k, v in rows:
        html.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
    html.append("</tbody></table>")
    st.markdown("\n".join(html), unsafe_allow_html=True)

def metrics_row(result):
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f"<div class='card'><h3>Avg Slope (LAH)</h3><p>{fmt_num(result['avg_slope_percent_LAH'],2)}%</p></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='card'><h3>Lot Unit Factor</h3><p>{fmt_num(result['lot_unit_factor'],6)}</p></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='card'><h3>MDA</h3><p>{fmt_num(result['mda_ft2'],1)} ft²</p></div>", unsafe_allow_html=True)
    m4.markdown(f"<div class='card'><h3>MFA</h3><p>{fmt_num(result['mfa_ft2'],1)} ft²</p></div>", unsafe_allow_html=True)

def download_buttons(result):
    json_bytes = json.dumps(result, indent=2).encode("utf-8")
    st.download_button("⬇️ Download JSON", json_bytes, file_name=f"lah_buildability_{result['apn']}.json", mime="application/json")
    df = pd.DataFrame(build_rows(result), columns=["Metric","Value"])
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv, file_name=f"lah_buildability_{result['apn']}.csv", mime="text/csv")

# ------------------------ Cached execution ------------------------
@st.cache_data(show_spinner=False, ttl=600)
def cached_run(mode: str, q: str, contour_interval_ft: float, qa_samples: int):
    if mode == "APN":
        return run_for_apn(q, contour_interval_ft)
    return run_for_address(q, contour_interval_ft)

# ------------------------ Run ------------------------
if run_btn:
    if not user_input.strip():
        st.warning("Please enter an address or APN.")
        st.stop()

    with st.spinner("Contacting County GIS services…"):
        try:
            result = cached_run(mode, user_input.strip(), float(ci), int(qa_samples))
        except requests.exceptions.ReadTimeout:
            st.error("⏳ GIS server timeout. Try again later.")
            st.stop()
        except requests.exceptions.ConnectionError:
            st.error("🌐 Connection error to County GIS. Check network or VPN.")
            st.stop()
        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.stop()

    # ---------------- Results Display ----------------
    st.success("✅ Analysis completed successfully.")
    badge = '<span class="badge ok">CDP Not Required</span>' if not result["requires_cdp"] else '<span class="badge warn">CDP Required</span>'
    st.markdown(badge, unsafe_allow_html=True)

    metrics_row(result)
    st.write("")

    with st.expander("Detailed Results", expanded=True):
        render_detail_table(build_rows(result))
        notes = result.get("notes", {})
        st.markdown(
            f"<div class='note'><b>Notes</b><br>"
            f"• Interval (selected/detected/used): {notes.get('contour_interval_ft_selected','—')} / "
            f"{notes.get('contour_interval_ft_detected','—')} / "
            f"{notes.get('contour_interval_ft_used','—')} ft<br>"
            f"• CDP rule: {notes.get('cdp_rule','—')}<br>"
            f"• Disclaimer: {notes.get('disclaimer','—')}</div>",
            unsafe_allow_html=True,
        )

    if show_diag:
        st.markdown("### Diagnostics")
        diag_cols = st.columns(2)
        with diag_cols[0]:
            st.markdown(
                f"<div class='kv'>elev_field = <b>{result.get('contour_elevation_field')}</b><br>"
                f"contour_count = <b>{result.get('contour_count')}</b><br>"
                f"total_length_ft = <b>{fmt_num(result.get('contour_total_length_ft'),1)}</b><br>"
                f"avg_slope_pct = <b>{fmt_num(result.get('avg_slope_percent_LAH'),2)}</b></div>",
                unsafe_allow_html=True,
            )
        with diag_cols[1]:
            st.markdown(
                f"<div class='kv'>parcel_area_ft2 = <b>{fmt_num(result.get('parcel_area_ft2'),1)}</b><br>"
                f"parcel_area_acres = <b>{fmt_num(result.get('parcel_area_acres'),4)}</b><br>"
                f"DEM slope QA mean (%) = <b>{fmt_num(result.get('slope_percent_dem_QA_mean'),2)}</b></div>",
                unsafe_allow_html=True,
            )

    st.write("")
    download_buttons(result)

# ------------------------ Footer ------------------------
st.write("")
st.markdown(
    "<div class='small'>Built by <b>Private Open House Inc.</b> • Logic mirrors the official Los Altos Hills worksheet. "
    "Confirm results with planning staff.</div>",
    unsafe_allow_html=True,
)
