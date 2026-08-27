import type { components } from "@/types/api";

type NarrativeType = components["schemas"]["Narrative"];

interface NarrativeProps {
  narrative: NarrativeType | null | undefined;
}

const PRIORITY_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/**
 * Four fields, each rendered distinctly (Phase3-Plan T3.3) — this is why the
 * shape is structured rather than a blob: actions render as a checklist,
 * positives get their own quiet treatment, and the whole thing degrades to
 * nothing when narrative is null (the caller in ResultsView handles that;
 * this component assumes it's only mounted when narrative exists).
 */
export function Narrative({ narrative }: NarrativeProps) {
  if (!narrative) return null;

  const sortedActions = [...narrative.prioritized_actions].sort(
    (a, b) => (PRIORITY_ORDER[a.priority] ?? 99) - (PRIORITY_ORDER[b.priority] ?? 99)
  );

  return (
    <section className="space-y-6">
      <p className="max-w-prose text-base leading-relaxed text-ink">{narrative.situation_summary}</p>

      {narrative.likely_root_causes.length > 0 && (
        <div>
          <h3 className="text-sm font-medium tracking-wide text-ink-muted uppercase">Likely root causes</h3>
          <ul className="mt-2 space-y-1.5">
            {narrative.likely_root_causes.map((cause, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink">
                <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-muted" />
                {cause}
              </li>
            ))}
          </ul>
        </div>
      )}

      {sortedActions.length > 0 && (
        <div>
          <h3 className="text-sm font-medium tracking-wide text-ink-muted uppercase">Prioritized actions</h3>
          <ul className="mt-2 space-y-2">
            {sortedActions.map((action, i) => (
              <li key={i} className="flex items-start gap-3 border-b border-rule pb-2 last:border-0">
                <span className="mt-0.5 shrink-0 rounded-sm border border-rule px-1.5 py-0.5 text-[11px] font-medium tracking-wide text-ink-muted uppercase">
                  {action.priority}
                </span>
                <div>
                  <p className="text-sm font-medium text-ink">{action.action}</p>
                  <p className="mt-0.5 text-sm text-ink-muted">{action.rationale}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {narrative.positives.length > 0 && (
        <div className="rounded-sm border border-rule bg-white/40 p-3">
          <h3 className="text-sm font-medium tracking-wide text-ink-muted uppercase">What&apos;s going well</h3>
          <ul className="mt-2 space-y-1">
            {narrative.positives.map((positive, i) => (
              <li key={i} className="text-sm leading-relaxed text-ink-muted">
                {positive}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
