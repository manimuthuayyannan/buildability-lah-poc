"""
LAH Worksheet math (Worksheet #1): S (avg slope), LUF, MDA, MFA.
All formulas mirror the Town’s worksheet.
"""

def average_slope_percent_lah(total_contour_len_ft: float, interval_ft: float, area_acres: float) -> float:
    # S (%) = 0.0023 * I(ft) * L(ft) / An(acres)
    if area_acres <= 0:
        return 0.0
    return 0.0023 * interval_ft * total_contour_len_ft / area_acres

def lot_unit_factor(area_acres: float, slope_percent: float) -> float:
    # LUF = An for S <= 10
    # LUF = An*(1 - 0.02143*(S-10)) for 10 < S < 30
    # Past 30% the Town caps with separate rules; practical site behavior uses same linear
    if slope_percent <= 10.0:
        return area_acres
    if slope_percent < 30.0:
        return area_acres * (1.0 - 0.02143*(slope_percent - 10.0))
    # Cap behavior (treat >=30 same as 30 for LUF)
    return area_acres * (1.0 - 0.02143*(30.0 - 10.0))

def mda_mfa_from_luf(slope_percent: float, LUF: float):
    # MDA
    if slope_percent <= 10.0:
        MDA = LUF * 15000.0
    elif slope_percent < 30.0:
        MDA = LUF * (15000.0 - 375.0*(slope_percent - 10.0))
    else:
        MDA = LUF * 7500.0

    # MFA
    if slope_percent <= 10.0:
        MFA = LUF * 6000.0
    elif slope_percent < 30.0:
        MFA = LUF * (6000.0 - 50.0*(slope_percent - 10.0))
    else:
        MFA = LUF * 5000.0

    # Minimum floors if LUF > 0.50
    if LUF > 0.50:
        MDA = max(MDA, 7500.0)
        MFA = max(MFA, 5000.0)

    requires_cdp = (LUF <= 0.50)
    return (round(MDA,1), round(MFA,1), requires_cdp)