/**
 * Hand-rolled SVG sparkline (Phase3-Plan §2) — values_over_time is at most a
 * dozen points, not worth a charting library.
 */
interface TrendPoint {
  period: string;
  value: number;
  z_score: number;
}

interface SparklineProps {
  points: TrendPoint[];
  width?: number;
  height?: number;
}

export function Sparkline({ points, width = 120, height = 32 }: SparklineProps) {
  if (!points || points.length < 2) return null;

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);

  const coords = points.map((p, i) => {
    const x = i * stepX;
    const y = height - ((p.value - min) / range) * (height - 4) - 2;
    return { x, y };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const last = coords[coords.length - 1];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      role="img"
      aria-label={`Trend sparkline across ${points.length} periods`}
    >
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last.x} cy={last.y} r={2} fill="var(--accent)" />
    </svg>
  );
}
