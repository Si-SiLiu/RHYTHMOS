"""Canonical row definition shared by today's Recovery and Feedback tables."""


MEASUREMENT_QUALITIES = ("GOOD", "ACCEPTABLE", "POOR", "INVALID")


def recovery_metrics_table_row(date_value, values, *, tr, language, format_date, ui):
    """Return the complete, ordered row used for recovery measurements.

    Keeping the column definitions here prevents the comprehensive feedback
    page from drifting away from the Today's Recovery Data table.
    """
    raw_quality = values.get("measurement_quality")
    quality = str(raw_quality).upper() if raw_quality not in (None, "") else None
    quality_display = (
        tr("domain.recovery.quality_" + quality.lower())
        if quality in MEASUREMENT_QUALITIES else tr("common.no_data")
    )
    return {
        tr("reports.date"): format_date(date_value, language),
        tr("domain.recovery.morning_rmssd"): values.get("morning_rmssd"),
        tr("domain.recovery.morning_resting_hr"): values.get("morning_mean_hr"),
        tr("kubios_metrics.pns.name"): values.get("pns_index"),
        tr("kubios_metrics.sns.name"): values.get("sns_index"),
        f'{tr("kubios_metrics.physiological_age.name")} ({ui("岁", "years")})': values.get("physiological_age"),
        f'{tr("kubios_metrics.mean_rr.name")} (ms)': values.get("mean_rr_ms"),
        f'{tr("kubios_metrics.sdnn.name")} (ms)': values.get("sdnn_ms"),
        f'{tr("kubios_metrics.sd1.name")} (ms)': values.get("poincare_sd1_ms"),
        f'{tr("kubios_metrics.sd2.name")} (ms)': values.get("poincare_sd2_ms"),
        tr("domain.recovery.stress_index"): values.get("stress_index"),
        tr("domain.recovery.respiratory_rate"): values.get("respiratory_rate"),
        f'{tr("kubios_metrics.lf_power.name")} (ms²)': values.get("lf_power_ms2"),
        f'{tr("kubios_metrics.hf_power.name")} (ms²)': values.get("hf_power_ms2"),
        f'{tr("kubios_metrics.lf_nu.name")} (%)': values.get("lf_power_nu"),
        f'{tr("kubios_metrics.hf_nu.name")} (%)': values.get("hf_power_nu"),
        tr("kubios_metrics.lf_hf.name"): values.get("lf_hf_ratio"),
        tr("domain.recovery.measurement_quality"): quality_display,
    }
