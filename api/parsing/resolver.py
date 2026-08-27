"""Alias resolver (Phase2-Plan T2.3 / master plan §6.2).

C1's resolver is exact-match after lower()+strip(). C2 owns fuzzy-via-
normalization matching because we're the only component with a live user —
ambiguity becomes a confirmation prompt rather than a silent guess.
"""

import re
from functools import lru_cache
from typing import Optional

from api.config.loader import metrics as load_metrics
from api.models.internal import MappingProposal, ParseWarning, ParseWarningCode
from api.models.shared import SectorId

_NON_ALPHANUMERIC_RE = re.compile(r"[^a-z0-9]")


def normalize(label: str) -> str:
    """lowercase -> strip non-alphanumerics -> collapse whitespace (there is
    none left to collapse once non-alphanumerics, including spaces, are
    stripped — that's the point: "MRR Growth (%)" / "mrr-growth" /
    "MRR_Growth" all collapse to "mrrgrowth")."""
    return _NON_ALPHANUMERIC_RE.sub("", label.lower())


@lru_cache(maxsize=1)
def _build_index() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """normalized_alias -> [distinct metric_id, ...], normalized_display_name
    -> [distinct metric_id, ...].

    Distinct, not append-blind: a metric can list two aliases that happen to
    normalize the same way (e.g. "MRR Growth" and "MRR Growth %" both ->
    "mrrgrowth") without that being an ambiguity — it's still one metric.
    Ambiguity is specifically when two DIFFERENT metrics land on one key.
    Cross-metric collisions are caught at config-load time by test_config.py.
    """
    alias_index: dict[str, list[str]] = {}
    display_name_index: dict[str, list[str]] = {}
    for metric_id, cfg in load_metrics().items():
        for alias in cfg.get("common_aliases", []):
            bucket = alias_index.setdefault(normalize(alias), [])
            if metric_id not in bucket:
                bucket.append(metric_id)
        bucket = display_name_index.setdefault(normalize(cfg["display_name"]), [])
        if metric_id not in bucket:
            bucket.append(metric_id)
    return alias_index, display_name_index


def resolve(
    label: str, sector_id: SectorId, sample_values: Optional[list[float]] = None
) -> tuple[MappingProposal, list[ParseWarning]]:
    """Resolution order, first hit wins: exact metric_id -> normalized alias
    -> normalized display_name -> unresolved. Sector membership is checked
    once a match is found; a match outside the submitted sector becomes
    SECTOR_MISMATCH, not a silent accept or a generic UNKNOWN_METRIC."""
    sample_values = sample_values or []
    all_metrics = load_metrics()

    def _resolved(metric_id: str, match_type: str) -> tuple[MappingProposal, list[ParseWarning]]:
        return (
            MappingProposal(
                source_label=label,
                resolved_metric_id=metric_id,
                match_type=match_type,
                sample_values=sample_values,
            ),
            [],
        )

    def _unresolved(
        code: ParseWarningCode, message: str, candidates: Optional[list[str]] = None
    ) -> tuple[MappingProposal, list[ParseWarning]]:
        return (
            MappingProposal(
                source_label=label,
                resolved_metric_id=None,
                match_type="unresolved",
                sample_values=sample_values,
                candidates=candidates or [],
            ),
            [ParseWarning(code=code, message=message)],
        )

    def _check_sector(metric_id: str, match_type: str) -> tuple[MappingProposal, list[ParseWarning]]:
        if sector_id.value not in all_metrics[metric_id]["sector_ids"]:
            return _unresolved(
                ParseWarningCode.SECTOR_MISMATCH,
                f"'{label}' resolves to '{metric_id}', which isn't offered for sector {sector_id.value}.",
            )
        return _resolved(metric_id, match_type)

    # 1. Exact metric_id match
    if label in all_metrics:
        return _check_sector(label, "exact")

    normalized_label = normalize(label)
    alias_index, display_name_index = _build_index()

    # 2. Normalized alias match, 3. normalized display_name match
    for index, match_type in ((alias_index, "alias"), (display_name_index, "normalized")):
        candidates = index.get(normalized_label, [])
        if len(candidates) > 1:
            return _unresolved(
                ParseWarningCode.AMBIGUOUS_MAPPING,
                f"'{label}' matched multiple metrics ({', '.join(candidates)}); confirm which one you meant.",
                candidates=candidates,
            )
        if len(candidates) == 1:
            return _check_sector(candidates[0], match_type)

    # 4. No match
    return _unresolved(ParseWarningCode.UNKNOWN_METRIC, f"Could not resolve column '{label}' to any known metric.")
