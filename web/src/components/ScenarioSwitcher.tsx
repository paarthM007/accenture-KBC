"use client";

import { SCENARIO_LABELS, type ScenarioName } from "@/lib/scenarios";

interface ScenarioSwitcherProps {
  onSelect: (scenario: ScenarioName) => void;
  onLiveDemo: () => void;
}

/**
 * A dev-only control that forces any of the four states deterministically
 * (Phase3-Plan T3.8) — protects the demo from having to hunt for the right
 * CSV on stage. Hidden entirely unless NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER=true.
 */
export function ScenarioSwitcher({ onSelect, onLiveDemo }: ScenarioSwitcherProps) {
  if (process.env.NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER !== "true") return null;

  return (
    <div className="fixed right-4 bottom-4 z-50 rounded-sm border border-rule bg-white/95 p-3 shadow-md backdrop-blur">
      <p className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">Scenario switcher (dev)</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {(Object.keys(SCENARIO_LABELS) as ScenarioName[]).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => onSelect(name)}
            className="rounded-sm border border-rule px-2 py-1 text-xs text-ink hover:border-accent hover:text-accent"
          >
            {SCENARIO_LABELS[name]}
          </button>
        ))}
        <button
          type="button"
          onClick={onLiveDemo}
          className="rounded-sm border border-rule px-2 py-1 text-xs text-ink-muted hover:border-accent hover:text-accent"
        >
          Live form
        </button>
      </div>
    </div>
  );
}
