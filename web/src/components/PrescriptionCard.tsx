import type { components } from "@/types/api";

type Prescription = components["schemas"]["Prescription"];

interface PrescriptionCardProps {
  prescription: Prescription;
}

/**
 * Phase3-Plan T3.5. current_value: null must render as "not currently
 * tracked" — never 0, never blank. This is Contract §6.4's whole point: we
 * recommend a lever without asserting a value we don't have.
 */
export function PrescriptionCard({ prescription }: PrescriptionCardProps) {
  return (
    <div className="border-t border-rule pt-4 first:border-0 first:pt-0">
      <p className="text-sm text-ink-muted">{prescription.prescription_summary}</p>
      <ul className="mt-3 space-y-3">
        {prescription.prescribed_adjustments.map((adjustment, i) => (
          <li key={i} className="rounded-sm border border-rule p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-ink">
                {adjustment.action === "DECREASE" ? "Decrease" : "Increase"} {adjustment.target_display_name}
              </p>
              <span className="shrink-0 rounded-sm border border-rule px-1.5 py-0.5 text-[11px] font-medium tracking-wide text-ink-muted uppercase">
                {adjustment.priority}
              </span>
            </div>

            <div className="data mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
              <span className="text-ink-muted">Current:</span>
              <span className={adjustment.current_value == null ? "text-ink-muted italic" : "text-ink"}>
                {adjustment.current_value == null ? "not currently tracked" : adjustment.current_value.toFixed(2)}
              </span>
              <span className="text-ink-muted">→ Target:</span>
              <span className="text-ink">{adjustment.target_value.toFixed(2)}</span>
              {adjustment.delta != null && (
                <span className="text-ink-muted">
                  ({adjustment.delta >= 0 ? "+" : ""}
                  {adjustment.delta.toFixed(2)})
                </span>
              )}
            </div>

            <p className="mt-2 text-xs text-ink-muted">{adjustment.rationale}</p>
            <p className="mt-1 text-[11px] text-ink-muted italic">basis: {adjustment.target_basis}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
