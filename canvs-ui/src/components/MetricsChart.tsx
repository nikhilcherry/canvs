import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MetricEvent } from "../types";

const SERIES_PALETTE = ["#6ea8fe", "#4ade80", "#fbbf24", "#f87171", "#c084fc", "#22d3ee", "#fb923c", "#f472b6"];

export function MetricsChart({ events, title }: { events: MetricEvent[]; title?: string }) {
  const metricEvents = events.filter((e) => e.event === "metric" && e.values);

  const seriesKeys = new Set<string>();
  const stepRows = new Map<number, Record<string, number>>();

  for (const e of metricEvents) {
    const step = e.step ?? 0;
    const row = stepRows.get(step) ?? { step };
    for (const [k, v] of Object.entries(e.values ?? {})) {
      const seriesKey = `${e.node}.${k}`;
      seriesKeys.add(seriesKey);
      row[seriesKey] = v;
    }
    stepRows.set(step, row);
  }

  const data = [...stepRows.values()].sort((a, b) => a.step - b.step);
  const keys = [...seriesKeys];

  if (data.length === 0) {
    return (
      <div className="metrics-chart-empty">
        {title && <div className="metrics-chart-title">{title}</div>}
        No metrics reported yet.
      </div>
    );
  }

  return (
    <div className="metrics-chart">
      {title && <div className="metrics-chart-title">{title}</div>}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="step" stroke="var(--muted)" fontSize={12} />
          <YAxis stroke="var(--muted)" fontSize={12} />
          <Tooltip
            contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)" }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} />
          {keys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={SERIES_PALETTE[i % SERIES_PALETTE.length]}
              dot={false}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
