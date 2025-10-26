from .config import ACRES_PER_FT2


def average_slope_percent_lah(total_contour_len_ft: float, contour_interval_ft: float, parcel_area_ft2: float):
    """
    Classic contour method:
    Avg Slope (%) = (Σ L × I × 100) / (A × 2)  --> with ΣL being total contour length (ft),
    I = contour interval (ft), A = area (ft²).
    """
    if not total_contour_len_ft or total_contour_len_ft <= 0 or not parcel_area_ft2 or parcel_area_ft2 <= 0:
        return None
    return (total_contour_len_ft * contour_interval_ft * 100.0) / (parcel_area_ft2 * 2.0)

def lot_unit_factor(area_acres, avg_slope_pct):
    if not area_acres or area_acres <= 0 or avg_slope_pct is None:
        return None
    S = min(max(avg_slope_pct, 0.0), 55.0)
    if S <= 10.0:
        return round(area_acres, 6)
    factor = 1.0 - 0.02143 * (S - 10.0)
    return round(area_acres * max(factor, 0.0), 6)

def mda_mfa_from_luf(avg_slope_pct, luf):
    if luf is None or avg_slope_pct is None:
        return None, None, None
    # CDP rule
    if luf <= 0.50:
        mfa = (luf / 0.50) * 5000.0
        mda = mfa + 2100.0
        return round(mda, 1), round(mfa, 1), True
    S = avg_slope_pct
    # MDA
    if S <= 10.0:
        mda = luf * 15000.0
    elif S < 30.0:
        mda = luf * (15000.0 - 375.0 * (S - 10.0))
    else:
        mda = luf * 7500.0
    # MFA
    if S <= 10.0:
        mfa = luf * 6000.0
    elif S < 30.0:
        mfa = luf * (6000.0 - 50.0 * (S - 10.0))
    else:
        mfa = luf * 5000.0
    # Minimums
    if luf > 0.50:
        mda = max(mda, 7500.0)
        mfa = max(mfa, 5000.0)
    return round(mda, 1), round(mfa, 1), False
