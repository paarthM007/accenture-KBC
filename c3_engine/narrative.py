import json
import logging
from typing import Optional, Tuple, Dict, Any
from .schemas import AnomalyReport, Prescription, MatchedCase, Narrative

logger = logging.getLogger(__name__)

def generate_narrative(
    anomaly_report: AnomalyReport,
    prescriptions: list[Prescription],
    matched_cases: list[MatchedCase]
) -> Tuple[Optional[Narrative], bool, dict]:
    """
    Generates situation summary, root causes, prioritized actions, and positives
    by calling the LLM (Gemini) in a structured JSON manner.
    
    If the API key is not configured, if the API call fails, if google.generativeai 
    is not installed, or if validation fails, it returns (None, True, {}) to 
    indicate degraded mode.
    """
    try:
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        from google import genai
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
            
        client = genai.Client(api_key=api_key)
        
        # Build prompt context
        profile = anomaly_report.company_profile_summary
        profile_summary = (
            f"Sector: {anomaly_report.sector_id}\n"
            f"Region: {profile.region}\n"
            f"Size: {profile.employee_count} employees\n"
            f"Revenue Band: {profile.revenue_band}"
        )
        
        anomalies_ctx = []
        for a in anomaly_report.anomalies:
            anomalies_ctx.append({
                "anomaly_id": a.anomaly_id,
                "metric_id": a.metric_id,
                "display_name": a.metric_display_name,
                "severity_label": a.severity_label,
                "observed": a.deviation.observed_current,
                "expected": a.deviation.expected_value,
                "summary": a.natural_language_summary
            })
            
        highlights_ctx = []
        for h in anomaly_report.non_anomalous_highlights:
            highlights_ctx.append({
                "metric_id": h.metric_id,
                "display_name": h.metric_display_name,
                "observed": h.observed_value,
                "expected": h.expected_value,
                "summary": h.natural_language_summary
            })
            
        presc_ctx = []
        for p in prescriptions:
            for adj in p.prescribed_adjustments:
                presc_ctx.append({
                    "anomaly_id": p.anomaly_id,
                    "target_metric": adj.target_metric_id,
                    "action": adj.action,
                    "current": adj.current_value,
                    "target": adj.target_value,
                    "priority": adj.priority,
                    "rationale": adj.rationale
                })
                
        cases_ctx = []
        for mc in matched_cases:
            cases_ctx.append({
                "case_id": mc.case_id,
                "similarity_score": mc.similarity_score,
                "description": mc.problem_description,
                "root_causes": mc.root_causes,
                "recommended_actions": mc.recommended_actions
            })
            
        prompt = f"""
You are a Business Intelligence Analyst. Generate a comprehensive business narrative analyzing the anomalies detected in our company performance.

--- COMPANY PROFILE ---
{profile_summary}

--- DETECTED ANOMALIES ---
{json.dumps(anomalies_ctx, indent=2)}

--- HEALTHY HIGHLIGHTS ---
{json.dumps(highlights_ctx, indent=2)}

--- PRESCRIBED ADJUSTMENTS ---
{json.dumps(presc_ctx, indent=2)}

--- MATCHED HISTORICAL CASES ---
{json.dumps(cases_ctx, indent=2)}

Please analyze the above context and output a JSON object containing:
1. situation_summary: A high-level synthesis of the current business situation.
2. likely_root_causes: A list of likely root causes based on anomalies and matched cases.
3. prioritized_actions: A list of prioritized action items. Each item must contain:
   - title: Short title of the action.
   - description: Detailed explanation.
   - impact: "HIGH", "MEDIUM", or "LOW"
   - effort: "HIGH", "MEDIUM", or "LOW"
4. positives: A list of positive performance highlights/strengths from the highlights.

Output MUST conform strictly to the required schema. No pre-text or post-text outside the JSON object.
"""

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": Narrative,
            }
        )
        
        if hasattr(response, "parsed") and response.parsed is not None:
            narrative_obj = response.parsed
        else:
            narrative_obj = Narrative.model_validate_json(response.text)
        
        token_metadata = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
            token_metadata = {
                "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
                "candidates_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
                "total_tokens": getattr(response.usage_metadata, "total_token_count", None)
            }
            
        return narrative_obj, False, {"llm_model": "gemini-3.1-flash-lite", "token_usage": token_metadata}
        
    except Exception as e:
        logger.warning(f"Narrative generation failed (degraded mode active): {e}")
        return None, True, {}
