/**
 * API client (Phase3-Plan T3.2). Four calls: validate(), analyzeUpload(),
 * analyzeJson(), health().
 *
 * Every call returns a Promise even though the backend is synchronous today.
 * Phase 1 documented the possible async job-polling swap; if Phase 4 measures
 * real C1+C3 latency above ~8s and that swap happens, only this file changes
 * — components must never assume the response is immediate.
 */
import type { components } from "@/types/api";

export type ApiResponse = components["schemas"]["ApiResponse"];
export type ValidateResponse = components["schemas"]["ValidateResponse"];
export type CompanyInput = components["schemas"]["CompanyInput"];
export type SectorId = components["schemas"]["SectorId"];
export type RevenueBand = components["schemas"]["RevenueBand"];

// FormMetadata is invisible to the OpenAPI schema — the backend receives it
// as an opaque JSON string inside a multipart field (see
// api/models/internal.py's FormMetadata), so it can't be generated. Hand-kept
// in sync with that model.
export interface FormMetadata {
  company_name: string;
  sector_id: SectorId;
  employee_count: number;
  region: string;
  founded_year?: number | null;
  annual_revenue?: number | null;
  revenue_band?: RevenueBand | null;
  raw_text_context?: string | null;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error(`Server returned a non-JSON response (HTTP ${response.status}).`);
  }
  // Both success and error paths (422, etc.) return a body we can hand back
  // to the caller — every backend error is a typed envelope, never a bare
  // stack trace (Contract §8) — so we don't throw on !response.ok here.
  return body as T;
}

export async function health(): Promise<{ status: string; [key: string]: unknown }> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return parseJsonOrThrow(response);
}

export async function analyzeJson(companyInput: CompanyInput): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(companyInput),
  });
  return parseJsonOrThrow<ApiResponse>(response);
}

export async function validate(file: File, metadata: FormMetadata): Promise<ValidateResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  const response = await fetch(`${API_BASE_URL}/validate`, { method: "POST", body: form });
  return parseJsonOrThrow<ValidateResponse>(response);
}

export async function analyzeUpload(
  file: File,
  metadata: FormMetadata,
  mappingOverrides?: Record<string, string>
): Promise<ApiResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  if (mappingOverrides && Object.keys(mappingOverrides).length > 0) {
    form.append("mapping_overrides", JSON.stringify(mappingOverrides));
  }
  const response = await fetch(`${API_BASE_URL}/analyze/upload`, { method: "POST", body: form });
  return parseJsonOrThrow<ApiResponse>(response);
}
