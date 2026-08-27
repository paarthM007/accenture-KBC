"use client";

import { useState } from "react";

interface DegradedBannerProps {
  degradedReason: string | null | undefined;
}

/**
 * Informational, not alarming (Phase3-Plan T3.6): "Narrative unavailable for
 * this run — findings below are complete." degraded_reason is operational
 * (c3_timeout, llm_failed) and belongs in a details disclosure, not in front
 * of a business user.
 */
export function DegradedBanner({ degradedReason }: DegradedBannerProps) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="rounded-sm border border-rule bg-white/50 px-4 py-3">
      <p className="text-sm text-ink">
        Narrative unavailable for this run — findings below are complete.
      </p>
      {degradedReason && (
        <button
          type="button"
          className="mt-1 text-xs text-ink-muted underline decoration-dotted underline-offset-2"
          onClick={() => setShowDetails((v) => !v)}
        >
          {showDetails ? `Details: ${degradedReason}` : "Details"}
        </button>
      )}
    </div>
  );
}
