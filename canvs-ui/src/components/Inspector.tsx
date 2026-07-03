import { useStore } from "../store";
import type { ParamSchema } from "../types";
import { MetricsChart } from "./MetricsChart";

function ConfigField({
  name,
  schema,
  value,
  onChange,
}: {
  name: string;
  schema: ParamSchema;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const isEmpty = value === undefined || value === null || value === "";
  const invalid = Boolean(schema.required) && isEmpty;

  let input: React.ReactNode;
  if (schema.enum) {
    input = (
      <select value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>
          select...
        </option>
        {schema.enum.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  } else if (schema.type === "boolean") {
    input = (
      <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
    );
  } else if (schema.type === "integer" || schema.type === "number") {
    input = (
      <input
        type="number"
        step={schema.type === "integer" ? 1 : "any"}
        value={value === undefined ? "" : (value as number)}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") {
            onChange(undefined);
            return;
          }
          onChange(schema.type === "integer" ? parseInt(raw, 10) : parseFloat(raw));
        }}
      />
    );
  } else {
    input = (
      <input type="text" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />
    );
  }

  return (
    <label className={`config-field${invalid ? " invalid" : ""}`}>
      <span className="config-field-name">
        {name}
        {schema.required && <span className="config-field-required">*</span>}
      </span>
      {input}
    </label>
  );
}

function RunView() {
  const run = useStore((s) => s.run);

  const timeline = run.events.filter((e) => e.event !== "metric");

  return (
    <div className="inspector-run-view">
      <div className="inspector-run-header">
        <span>Run {run.runId}</span>
        <span className={`run-status status-${run.status}`}>{run.status}</span>
      </div>

      <MetricsChart events={run.events} title="Metrics" />

      <div className="inspector-section">
        <div className="inspector-section-title">Timeline</div>
        <div className="timeline">
          {timeline.map((e) => (
            <div key={e.id} className={`timeline-row event-${e.event}`}>
              <span className="timeline-event">{e.event}</span>
              {e.node && <span className="timeline-node">{e.node}</span>}
              {e.payload && "error" in e.payload && (
                <span className="timeline-error">{String(e.payload.error)}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {run.target === "local" && (
        <div className="inspector-section">
          <div className="inspector-section-title">Log</div>
          <pre className="log-tail">{run.log.join("\n")}</pre>
        </div>
      )}
    </div>
  );
}

export function Inspector() {
  const selectedNodeId = useStore((s) => s.selectedNodeId);
  const nodes = useStore((s) => s.nodes);
  const updateConfig = useStore((s) => s.updateConfig);
  const deleteNode = useStore((s) => s.deleteNode);
  const run = useStore((s) => s.run);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNode) {
    if (run.runId) return <RunView />;
    return <div className="inspector-empty">Select a node to configure it.</div>;
  }

  const { spec, config, metrics } = selectedNode.data;
  const paramEntries = Object.entries(spec.params).filter(([name]) => !name.startsWith("_"));

  return (
    <div className="inspector-node">
      <div className="inspector-node-header">
        <h3>{spec.name}</h3>
        <button className="btn-danger" onClick={() => deleteNode(selectedNode.id)}>
          Delete
        </button>
      </div>
      {spec.description && <p className="inspector-node-description">{spec.description}</p>}

      <div className="config-form">
        {paramEntries.length === 0 && <div className="config-form-empty">No configurable params.</div>}
        {paramEntries.map(([name, schema]) => (
          <ConfigField
            key={name}
            name={name}
            schema={schema}
            value={config[name]}
            onChange={(v) => updateConfig(selectedNode.id, name, v)}
          />
        ))}
      </div>

      {metrics.length > 0 && <MetricsChart events={metrics.map((m, i) => ({
        id: i,
        event: "metric" as const,
        node: selectedNode.id,
        step: m.step,
        values: m.values,
        payload: null,
        created_at: 0,
      }))} title="Node metrics" />}
    </div>
  );
}
