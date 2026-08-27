/**
 * The signature element (Phase3-Plan §1). Every anomaly carries both
 * severity_score (how bad) and noise_confidence (how sure) — almost no BI
 * tool shows the second. A horizontal bar whose fill length is severity and
 * whose edge treatment is confidence: a hard edge at high confidence, a
 * soft/hatched fade at low. One repeated, disciplined element that encodes
 * the product's entire thesis.
 */
interface SeverityConfidenceBarProps {
  severityScore: number; // 0-100
  noiseConfidence: number; // 0-1
}

export function SeverityConfidenceBar({ severityScore, noiseConfidence }: SeverityConfidenceBarProps) {
  const fillPct = Math.max(0, Math.min(100, severityScore));
  const confidence = Math.max(0, Math.min(1, noiseConfidence));
  // Higher confidence -> a near-instant transition (a hard edge). Lower
  // confidence -> a wide fade zone, softened further by the hatch overlay.
  const fadeWidthPct = 1.5 + (1 - confidence) * 16;
  const fadeStartPct = Math.max(0, fillPct - fadeWidthPct);

  return (
    <div className="w-full">
      <div
        className="relative h-3 w-full overflow-hidden rounded-[2px] bg-rule"
        role="img"
        aria-label={`Severity ${fillPct.toFixed(0)} of 100, confidence ${(confidence * 100).toFixed(0)} percent`}
      >
        <div
          className="absolute inset-y-0 left-0 bg-flag"
          style={{
            width: `${fillPct}%`,
            maskImage: `linear-gradient(to right, black 0%, black ${fadeStartPct}%, transparent ${fillPct}%)`,
            WebkitMaskImage: `linear-gradient(to right, black 0%, black ${fadeStartPct}%, transparent ${fillPct}%)`,
          }}
        />
        {confidence < 0.75 && fillPct - fadeStartPct > 0.5 && (
          <div
            className="absolute inset-y-0"
            style={{
              left: `${fadeStartPct}%`,
              width: `${fillPct - fadeStartPct}%`,
              opacity: 1 - confidence,
              backgroundImage:
                "repeating-linear-gradient(45deg, var(--flag) 0px, var(--flag) 2px, transparent 2px, transparent 5px)",
            }}
          />
        )}
      </div>
      <div className="data mt-1 flex justify-between text-xs text-ink-muted">
        <span>Severity {fillPct.toFixed(0)}</span>
        <span>Confidence {(confidence * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}
