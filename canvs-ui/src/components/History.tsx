import { useEffect } from "react";
import { useStore } from "../store";

const TARGET_ICON: Record<string, string> = {
  local: "💻",
  kaggle: "📊",
  colab: "📓",
};

function relativeTime(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const diffMinutes = Math.round((Date.now() - then) / 60000);
  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const hours = Math.round(diffMinutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function History() {
  const historyRuns = useStore((s) => s.historyRuns);
  const loadHistory = useStore((s) => s.loadHistory);
  const viewHistoryRun = useStore((s) => s.viewHistoryRun);
  const restoreHistoryGraph = useStore((s) => s.restoreHistoryGraph);
  const activeRunId = useStore((s) => s.run.runId);
  const readOnly = useStore((s) => s.run.readOnly);

  useEffect(() => {
    loadHistory().catch(() => {});
  }, [loadHistory]);

  return (
    <div className="history-panel">
      <div className="history-header">
        <span>Run history</span>
        <button onClick={() => loadHistory().catch(() => {})}>Refresh</button>
      </div>
      <div className="history-list">
        {historyRuns.length === 0 && <div className="history-empty">No runs yet.</div>}
        {historyRuns.map((r) => {
          const selected = readOnly && activeRunId === r.run_id;
          return (
            <div
              key={r.run_id}
              className={`history-item${selected ? " selected" : ""}`}
              onClick={() => viewHistoryRun(r.run_id)}
            >
              <div className="history-item-row">
                <span className="history-item-name">
                  {TARGET_ICON[r.target] ?? ""} {r.name}
                </span>
                <span className={`history-item-status status-${r.status}`}>{r.status}</span>
              </div>
              <div className="history-item-row">
                <span className="history-item-time">{relativeTime(r.created_at)}</span>
              </div>
              {selected && (
                <button
                  className="history-restore-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    restoreHistoryGraph(r.run_id);
                  }}
                >
                  Restore graph
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
