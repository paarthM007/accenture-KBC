"""T0.9 — config/metric_config.yaml loads and is internally consistent."""

from api.config.loader import load_metric_config, metrics, revenue_bands, thresholds
from api.parsing.resolver import normalize

REQUIRED_FIELDS = {"display_name", "unit", "valid_min", "valid_max", "direction", "sector_ids"}


def test_yaml_loads():
    config = load_metric_config()
    assert "metrics" in config
    assert "thresholds" in config
    assert "revenue_bands" in config


def test_all_13_metrics_present():
    assert len(metrics()) == 13


def test_every_metric_has_required_fields_and_at_least_one_alias():
    for metric_id, metric in metrics().items():
        missing = REQUIRED_FIELDS - metric.keys()
        assert not missing, f"{metric_id} is missing fields: {missing}"
        assert len(metric.get("common_aliases", [])) >= 1, f"{metric_id} has no aliases"


def test_shared_metrics_list_both_sectors():
    for metric_id in ("gross_margin", "customer_acquisition_cost"):
        sector_ids = set(metrics()[metric_id]["sector_ids"])
        assert sector_ids == {"TECH_SAAS", "RETAIL"}, f"{metric_id} sector_ids: {sector_ids}"


def test_no_duplicate_aliases_across_metrics():
    """Phase2-Plan T2.3: extended to check NORMALISED duplicates (using the
    real resolver.normalize(), not a loose .strip().lower()) since "CAC" and
    "C.A.C." only collide once non-alphanumerics are stripped.

    Only a CROSS-metric collision is a bug — a metric listing two aliases
    that happen to normalize the same way (e.g. "MRR Growth" and
    "MRR Growth %" both -> "mrrgrowth") is harmless redundancy, not
    ambiguity, since both still resolve to the one metric.
    """
    seen: dict[str, str] = {}
    for metric_id, metric in metrics().items():
        for alias in metric.get("common_aliases", []):
            key = normalize(alias)
            assert seen.get(key, metric_id) == metric_id, (
                f"alias {alias!r} (for {metric_id!r}) normalizes the same as an alias already "
                f"claimed by {seen.get(key)!r} — resolver would become non-deterministic"
            )
            seen[key] = metric_id


def test_no_duplicate_normalized_display_names():
    seen: dict[str, str] = {}
    for metric_id, metric in metrics().items():
        key = normalize(metric["display_name"])
        assert key not in seen, (
            f"display_name {metric['display_name']!r} normalizes the same as {seen.get(key)!r}'s"
        )
        seen[key] = metric_id


def test_thresholds_cover_all_granularities():
    min_periods = thresholds()["min_periods"]
    for granularity in ("monthly", "quarterly", "annual"):
        assert {"hard_block", "soft_warn", "full_trend"} <= min_periods[granularity].keys()


def test_revenue_bands_cover_full_range_with_no_gaps():
    bands = sorted(revenue_bands(), key=lambda b: b["min"])
    assert bands[0]["min"] == 0
    assert bands[-1]["max"] is None
    for earlier, later in zip(bands, bands[1:]):
        assert earlier["max"] == later["min"], "revenue bands must be contiguous"
