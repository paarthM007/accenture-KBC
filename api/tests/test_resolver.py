"""T2.3 — alias resolver. Exit criterion 3: messy headers all resolve to the
same canonical metric_id."""

import pytest

from api.models.internal import ParseWarningCode
from api.models.shared import SectorId
from api.parsing.resolver import normalize, resolve


class TestNormalize:
    def test_collisions(self):
        assert normalize("MRR Growth (%)") == normalize("mrr-growth") == normalize("MRR_Growth")
        assert normalize("MRR Growth (%)") == "mrrgrowth"


class TestResolve:
    @pytest.mark.parametrize(
        "label",
        ["MRR Growth %", "mrr-growth", "Monthly_Recurring_Revenue_Growth", "MRR"],
    )
    def test_messy_headers_resolve_to_canonical_id(self, label):
        proposal, warnings = resolve(label, SectorId.TECH_SAAS)
        assert proposal.resolved_metric_id == "monthly_recurring_revenue_growth"
        assert warnings == []

    def test_exact_metric_id_match(self):
        proposal, warnings = resolve("churn_rate", SectorId.TECH_SAAS)
        assert proposal.resolved_metric_id == "churn_rate"
        assert proposal.match_type == "exact"

    def test_display_name_match(self):
        proposal, warnings = resolve("Churn Rate (%)", SectorId.TECH_SAAS)
        assert proposal.resolved_metric_id == "churn_rate"
        assert proposal.match_type == "normalized"

    def test_unknown_column(self):
        proposal, warnings = resolve("Total Widgets Frobnicated", SectorId.TECH_SAAS)
        assert proposal.resolved_metric_id is None
        assert proposal.match_type == "unresolved"
        assert warnings[0].code == ParseWarningCode.UNKNOWN_METRIC

    def test_sector_mismatch(self):
        # same_store_sales_growth is RETAIL-only
        proposal, warnings = resolve("Comp Sales", SectorId.TECH_SAAS)
        assert proposal.resolved_metric_id is None
        assert warnings[0].code == ParseWarningCode.SECTOR_MISMATCH

    def test_shared_metric_resolves_for_both_sectors(self):
        for sector in (SectorId.TECH_SAAS, SectorId.RETAIL):
            proposal, warnings = resolve("CAC", sector)
            assert proposal.resolved_metric_id == "customer_acquisition_cost"
            assert warnings == []

    def test_ambiguous_mapping_never_auto_accepted(self):
        # Contrive a genuine collision by resolving the same normalized alias
        # against two entries — simulate via a label that would only collide
        # if the config had a bug. Since our config has none (test_config.py
        # guards it), we instead verify the *mechanism* the resolver would
        # use by monkeypatching the index directly.
        import api.parsing.resolver as resolver_module

        resolver_module._build_index.cache_clear()
        original = resolver_module._build_index
        try:
            resolver_module._build_index = lambda: (
                {"ambiguousthing": ["churn_rate", "gross_margin"]},
                {},
            )
            proposal, warnings = resolve("Ambiguous Thing", SectorId.TECH_SAAS)
            assert proposal.resolved_metric_id is None
            assert proposal.match_type == "unresolved"
            assert set(proposal.candidates) == {"churn_rate", "gross_margin"}
            assert warnings[0].code == ParseWarningCode.AMBIGUOUS_MAPPING
        finally:
            resolver_module._build_index = original
