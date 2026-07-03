import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useState } from "react";
import { hashCategoryColor, type CanvsNode as CanvsNodeType } from "../store";
import { useStore } from "../store";

const STATUS_ICON: Record<string, string> = {
  idle: "○",
  running: "●",
  done: "✓",
  failed: "✗",
};

function Sparkline({ points }: { points: { step: number; values: Record<string, number> }[] }) {
  const losses = points.filter((p) => "loss" in p.values).map((p) => p.values.loss);
  if (losses.length < 2) return null;

  const min = Math.min(...losses);
  const max = Math.max(...losses);
  const span = max - min || 1;
  const w = 160;
  const h = 28;
  const stepX = w / (losses.length - 1);

  const pointsStr = losses
    .map((v, i) => `${(i * stepX).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`)
    .join(" ");

  return (
    <svg className="node-sparkline" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={pointsStr} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
    </svg>
  );
}

export function CanvsNode({ id, data, selected }: NodeProps<CanvsNodeType>) {
  const [showErrors, setShowErrors] = useState(false);
  const selectNode = useStore((s) => s.selectNode);
  const color = hashCategoryColor(data.spec.category);
  const hasLoss = data.metrics.some((p) => "loss" in p.values);

  return (
    <div className={`canvs-node status-${data.status}${selected ? " selected" : ""}`}>
      <div className="canvs-node-accent" style={{ background: color }} />
      <div className="canvs-node-header">
        <span className="canvs-node-name">{data.spec.name}</span>
        <span className={`canvs-node-status status-${data.status}`} title={data.status}>
          {STATUS_ICON[data.status]}
        </span>
        {data.errors.length > 0 && (
          <span
            className="canvs-node-error-badge"
            onMouseEnter={() => setShowErrors(true)}
            onMouseLeave={() => setShowErrors(false)}
          >
            {data.errors.length}
            {showErrors && (
              <div className="canvs-node-error-tooltip">
                {data.errors.map((e, i) => (
                  <div key={i}>{e.message}</div>
                ))}
              </div>
            )}
          </span>
        )}
      </div>

      <div className="canvs-node-body">
        {data.spec.inputs.map((input, i) => (
          <div className="canvs-node-port" key={input}>
            <Handle
              type="target"
              position={Position.Left}
              id={input}
              style={{ top: `${((i + 1) / (data.spec.inputs.length + 1)) * 100}%` }}
            />
            <span className="canvs-node-port-label">{input}</span>
          </div>
        ))}

        {hasLoss && (
          <div className="canvs-node-sparkline-wrap" onClick={() => selectNode(id)}>
            <Sparkline points={data.metrics} />
          </div>
        )}
      </div>

      {data.spec.outputs.length > 0 && <Handle type="source" position={Position.Right} id="output" />}
    </div>
  );
}
