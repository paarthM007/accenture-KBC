/**
 * Static ApiResponse snapshots for the demo scenario switcher (T3.8).
 *
 * "No new backend endpoints" (Phase3-Plan) rules out a live runtime-scenario
 * endpoint, and MOCK_SCENARIO is a server-process-level setting the frontend
 * can't reach anyway. So the switcher swaps between calling the real API and
 * returning one of these four canned snapshots — generated once from the
 * same fixture builders and mocks the backend itself uses
 * (scripts/dump_scenario_responses.py), not hand-authored — so they can
 * never silently drift from what the mocks actually produce.
 */
import type { ApiResponse } from "./api";
import healthy from "./scenario-fixtures/healthy.json";
import critical from "./scenario-fixtures/critical.json";
import refusal from "./scenario-fixtures/refusal.json";
import degraded from "./scenario-fixtures/degraded.json";

export type ScenarioName = "healthy" | "critical" | "refusal" | "degraded";

export const SCENARIOS: Record<ScenarioName, ApiResponse> = {
  healthy: healthy as ApiResponse,
  critical: critical as ApiResponse,
  refusal: refusal as ApiResponse,
  degraded: degraded as ApiResponse,
};

export const SCENARIO_LABELS: Record<ScenarioName, string> = {
  healthy: "Healthy",
  critical: "Critical (SEVERE)",
  refusal: "Refusal",
  degraded: "Degraded (LLM failed)",
};
