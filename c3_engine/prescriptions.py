from typing import List, Tuple, Optional, Dict, Any
from .schemas import AnomalyReport, Anomaly, Prescription, Adjustment

# Rule configuration mapping: (sector_id, metric_id) -> (display_name, action, direction_symbol, rationale)
RULE_TABLE: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {
    # TECH_SAAS sector rules
    ("TECH_SAAS", "monthly_recurring_revenue_growth"): (
        "Monthly Recurring Revenue Growth",
        "INCREASE",
        "+",
        "Accelerate monthly recurring revenue growth to meet synthetic profile benchmarks and drive top-line momentum."
    ),
    ("TECH_SAAS", "churn_rate"): (
        "Churn Rate",
        "DECREASE",
        "-",
        "Reduce customer churn rate to stabilize the recurring revenue base and prevent customer attrition leakage."
    ),
    ("TECH_SAAS", "customer_acquisition_cost"): (
        "Customer Acquisition Cost",
        "DECREASE",
        "-",
        "Optimize marketing channels and sales efficiency to bring customer acquisition costs in line with the cohort baseline."
    ),
    ("TECH_SAAS", "lifetime_value"): (
        "Lifetime Value",
        "INCREASE",
        "+",
        "Maximize customer lifetime value through targeted expansion revenue, upselling, and retention efforts."
    ),
    ("TECH_SAAS", "net_revenue_retention"): (
        "Net Revenue Retention",
        "INCREASE",
        "+",
        "Improve net revenue retention by driving customer expansion and mitigating downgrades and churn."
    ),
    ("TECH_SAAS", "burn_rate"): (
        "Burn Rate",
        "DECREASE",
        "-",
        "Optimize operating expenses and burn rate to extend cash runway and enhance capital efficiency."
    ),
    ("TECH_SAAS", "gross_margin"): (
        "Gross Margin",
        "INCREASE",
        "+",
        "Enhance gross margin by optimizing hosting costs, COGS, and service delivery efficiency."
    ),

    # RETAIL sector rules (all 8 retail metrics)
    ("RETAIL", "gross_margin"): (
        "Gross Margin",
        "INCREASE",
        "+",
        "Optimize pricing strategy, manage COGS, and renegotiate supplier terms to address retail margin compression."
    ),
    ("RETAIL", "inventory_turnover"): (
        "Inventory Turnover",
        "INCREASE",
        "+",
        "Accelerate inventory turnover velocity to free up working capital and reduce dead-stock holding costs."
    ),
    ("RETAIL", "average_order_value"): (
        "Average Order Value",
        "INCREASE",
        "+",
        "Implement cross-selling, upselling, and bundle promotions to increase basket size and average order value."
    ),
    ("RETAIL", "revenue_per_sqft"): (
        "Revenue per Sq Ft",
        "INCREASE",
        "+",
        "Improve store layout, merchandising efficiency, and footfall conversions to enhance store productivity."
    ),
    ("RETAIL", "same_store_sales_growth"): (
        "Same Store Sales Growth",
        "INCREASE",
        "+",
        "Drive same-store sales growth via local store marketing, loyalty program engagement, and optimized assortments."
    ),
    ("RETAIL", "sell_through_rate"): (
        "Sell-Through Rate",
        "INCREASE",
        "+",
        "Optimize clearance promotions, markdown cadence, and inventory allocation to improve sell-through efficiency."
    ),
    ("RETAIL", "customer_acquisition_cost"): (
        "Customer Acquisition Cost",
        "DECREASE",
        "-",
        "Improve digital marketing efficiency, refine audience targeting, and lower customer acquisition costs."
    ),
    ("RETAIL", "return_rate"): (
        "Return Rate",
        "DECREASE",
        "-",
        "Address product return leakage by improving product sizing guides, description accuracy, and quality control."
    ),
}

def get_priority(severity_label: str) -> str:
    """
    Derives prescription priority from the anomaly severity label:
    - CRITICAL or SEVERE -> HIGH
    - WARNING -> MEDIUM
    - INFO -> LOW
    """
    label = severity_label.upper()
    if label in ("CRITICAL", "SEVERE"):
        return "HIGH"
    elif label == "WARNING":
        return "MEDIUM"
    else:
        return "LOW"

def find_submitted_metric_value(
    anomaly_report: AnomalyReport,
    target_metric_id: str,
    current_anomaly: Anomaly
) -> Tuple[Optional[float], str]:
    """
    Checks whether the target metric was submitted. If found in the anomaly report
    (either as the current anomaly, another anomaly, or in healthy highlights),
    returns its value and 'submitted'. Otherwise returns None and 'not_available'.
    """
    if target_metric_id == current_anomaly.metric_id:
        return current_anomaly.deviation.observed_current, "submitted"

    for anomaly in anomaly_report.anomalies:
        if anomaly.metric_id == target_metric_id:
            return anomaly.deviation.observed_current, "submitted"

    for highlight in anomaly_report.non_anomalous_highlights:
        if highlight.metric_id == target_metric_id:
            if highlight.observed_value is not None:
                return highlight.observed_value, "submitted"

    return None, "not_available"

def format_value(value: float, metric_id: str) -> str:
    """Formats values nicely for the summary text."""
    lower_id = metric_id.lower()
    if any(k in lower_id for k in ("rate", "margin", "growth", "percentile", "retention", "share", "ratio")):
        # If it looks like a percentage (typically between 0 and 1 or 0 and 100)
        return f"{value:.2f}%"
    elif any(k in lower_id for k in ("cost", "revenue", "spend", "burn", "value")):
        return f"${value:,.2f}"
    else:
        return f"{value:.2f}"

def build_prescription(
    anomaly_report: AnomalyReport,
    anomaly: Anomaly,
    unmatched_ids: List[str]
) -> Optional[Prescription]:
    """
    Generates a deterministic prescription for the given anomaly using the rule table.
    Appends anomaly_id to unmatched_ids and returns None if no rule matches.
    """
    sector_id = anomaly_report.sector_id
    metric_id = anomaly.metric_id
    rule_key = (sector_id, metric_id)

    if rule_key not in RULE_TABLE:
        unmatched_ids.append(anomaly.anomaly_id)
        return None

    display_name, action, direction_symbol, rationale = RULE_TABLE[rule_key]

    # Current value guardrail (§6.4)
    current_value, current_value_source = find_submitted_metric_value(
        anomaly_report, metric_id, anomaly
    )

    # Expected value from report (already band-adjusted synthetic baseline)
    target_value = anomaly.deviation.expected_value
    target_basis = "profile_baseline"

    # Compute delta if current value is available
    delta = None
    if current_value is not None:
        delta = target_value - current_value

    priority = get_priority(anomaly.severity_label)

    adjustment = Adjustment(
        target_metric_id=metric_id,
        target_display_name=display_name,
        action=action,
        direction_symbol=direction_symbol,
        current_value=current_value,
        current_value_source=current_value_source,
        target_value=target_value,
        target_basis=target_basis,
        delta=delta,
        priority=priority,
        rationale=rationale
    )

    # Format the summary text
    current_str = format_value(current_value, metric_id) if current_value is not None else "N/A"
    target_str = format_value(target_value, metric_id)
    summary_text = (
        f"Corrective adjustment prescribed for {display_name} to move from "
        f"{current_str} to the baseline target of {target_str} (priority: {priority})."
    )

    return Prescription(
        anomaly_id=anomaly.anomaly_id,
        prescribed_adjustments=[adjustment],
        prescription_summary=summary_text
    )
