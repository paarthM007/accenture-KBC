"use client";

import { useState } from "react";
import type { components } from "@/types/api";

type MatchedCase = components["schemas"]["MatchedCase"];

interface MatchedCasesProps {
  cases: MatchedCase[];
}

/** Collapsed by default, expandable (Phase3-Plan T3.5). Similarity shown honestly. */
export function MatchedCases({ cases }: MatchedCasesProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (cases.length === 0) return null;

  return (
    <ul className="space-y-2">
      {cases.map((matchedCase) => {
        const isOpen = openId === matchedCase.case_id;
        return (
          <li key={matchedCase.case_id} className="rounded-sm border border-rule">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 p-3 text-left"
              onClick={() => setOpenId(isOpen ? null : matchedCase.case_id)}
              aria-expanded={isOpen}
            >
              <span className="text-sm text-ink">{matchedCase.problem_description}</span>
              <span className="data shrink-0 text-xs text-ink-muted">
                {(matchedCase.similarity_score * 100).toFixed(0)}% match
              </span>
            </button>
            {isOpen && (
              <div className="space-y-2 border-t border-rule p-3 text-sm">
                <div>
                  <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Root causes</p>
                  <ul className="mt-1 list-inside list-disc text-ink-muted">
                    {matchedCase.root_causes.map((cause, i) => (
                      <li key={i}>{cause}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                    Recommended actions
                  </p>
                  <ul className="mt-1 list-inside list-disc text-ink-muted">
                    {matchedCase.recommended_actions.map((action, i) => (
                      <li key={i}>{action}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
