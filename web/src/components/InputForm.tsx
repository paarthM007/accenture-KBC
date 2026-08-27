"use client";

import { useState } from "react";
import type { FormMetadata, SectorId } from "@/lib/api";
import { previewRevenueBand } from "@/lib/revenueBand";

interface InputFormProps {
  onSubmit: (file: File, metadata: FormMetadata) => void;
  isSubmitting: boolean;
}

const SECTORS: { value: SectorId; label: string }[] = [
  { value: "TECH_SAAS", label: "Tech / SaaS" },
  { value: "RETAIL", label: "Retail" },
];

/**
 * Company name, sector dropdown, employee count, annual revenue, region,
 * plus the file input (Phase3-Plan T3.8). Shows the derived revenue band
 * live as the user types — makes the derivation visible rather than hidden.
 */
export function InputForm({ onSubmit, isSubmitting }: InputFormProps) {
  const [companyName, setCompanyName] = useState("");
  const [sectorId, setSectorId] = useState<SectorId>("TECH_SAAS");
  const [employeeCount, setEmployeeCount] = useState("");
  const [annualRevenue, setAnnualRevenue] = useState("");
  const [region, setRegion] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const revenueNumber = annualRevenue.trim() === "" ? null : Number(annualRevenue);
  const band = previewRevenueBand(revenueNumber);

  const canSubmit = companyName.trim() !== "" && employeeCount.trim() !== "" && region.trim() !== "" && file !== null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    onSubmit(file, {
      company_name: companyName,
      sector_id: sectorId,
      employee_count: Number(employeeCount),
      region,
      annual_revenue: revenueNumber,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-prose space-y-6 py-8">
      <div>
        <h2 className="font-display text-2xl font-medium text-ink">Submit your metrics</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Upload a CSV of your recent business metrics — wide or transposed, either works.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Company name">
          <input
            className="w-full rounded-sm border border-rule bg-white px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            required
          />
        </Field>
        <Field label="Sector">
          <select
            className="w-full rounded-sm border border-rule bg-white px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            value={sectorId}
            onChange={(e) => setSectorId(e.target.value as SectorId)}
          >
            {SECTORS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Employee count">
          <input
            type="number"
            min={1}
            className="data w-full rounded-sm border border-rule bg-white px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            value={employeeCount}
            onChange={(e) => setEmployeeCount(e.target.value)}
            required
          />
        </Field>
        <Field label="Region">
          <input
            className="w-full rounded-sm border border-rule bg-white px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="US"
            required
          />
        </Field>
        <Field label="Annual revenue ($)" hint={band ? `derived band: ${band}` : undefined}>
          <input
            type="number"
            min={0}
            className="data w-full rounded-sm border border-rule bg-white px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            value={annualRevenue}
            onChange={(e) => setAnnualRevenue(e.target.value)}
          />
        </Field>
      </div>

      <Field label="Metrics file (CSV)">
        <input
          type="file"
          accept=".csv"
          className="w-full text-sm text-ink-muted file:mr-3 file:rounded-sm file:border file:border-rule file:bg-white file:px-3 file:py-1.5 file:text-sm file:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
      </Field>

      <button
        type="submit"
        disabled={!canSubmit || isSubmitting}
        className="rounded-sm border border-ink bg-ink px-4 py-2 text-sm font-medium text-ground disabled:cursor-not-allowed disabled:border-rule disabled:bg-rule disabled:text-ink-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {isSubmitting ? "Reading file…" : "Continue"}
      </button>
    </form>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium tracking-wide text-ink-muted uppercase">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="data mt-1 block text-xs text-accent">{hint}</span>}
    </label>
  );
}
