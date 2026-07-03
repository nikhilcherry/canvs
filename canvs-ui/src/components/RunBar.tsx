import { useState } from "react";
import { useStore } from "../store";
import type { RunTarget } from "../types";

const TARGETS: RunTarget[] = ["local", "kaggle", "colab"];

const KAGGLE_INSTRUCTIONS =
  "Upload to Kaggle → attach dataset → enable GPU → set SUPABASE_URL/KEY as Kaggle secrets → Run all.";

export function RunBar() {
  const target = useStore((s) => s.run.target);
  const runStatus = useStore((s) => s.run.status);
  const runId = useStore((s) => s.run.runId);
  const showInstructions = useStore((s) => s.run.showInstructions);
  const validationErrors = useStore((s) => s.validationErrors);
  const polling = useStore((s) => s.run.polling);

  const validateNow = useStore((s) => s.validateNow);
  const startRun = useStore((s) => s.startRun);
  const killActiveRun = useStore((s) => s.killActiveRun);
  const dismissInstructions = useStore((s) => s.dismissInstructions);
  const setTarget = (t: RunTarget) => useStore.setState((s) => ({ run: { ...s.run, target: t } }));

  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const busy = runId !== null && (runStatus === "pending" || runStatus === "running");

  const handleValidate = async () => {
    const valid = await validateNow();
    setValidateMsg(valid ? "Graph is valid" : `${useStore.getState().validationErrors.length} error(s)`);
    setTimeout(() => setValidateMsg(null), 4000);
  };

  return (
    <div className="run-bar">
      <select value={target} onChange={(e) => setTarget(e.target.value as RunTarget)} disabled={busy}>
        {TARGETS.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      <button onClick={handleValidate} disabled={busy}>
        Validate
      </button>
      <button className="btn-primary" onClick={() => startRun(target)} disabled={busy}>
        Run
      </button>
      {busy && (
        <button className="btn-danger" onClick={() => killActiveRun()}>
          Kill
        </button>
      )}

      {validateMsg && (
        <span className={validationErrors.length ? "run-bar-msg error" : "run-bar-msg ok"}>
          {validateMsg}
        </span>
      )}

      {runId && (
        <span className={`run-bar-status status-${runStatus}`}>
          {polling ? "polling · " : ""}
          {runStatus}
        </span>
      )}

      {showInstructions && (
        <div className="instructions-card">
          <span>{target === "kaggle" ? KAGGLE_INSTRUCTIONS : "Open the downloaded notebook in Colab and run all cells."}</span>
          <button onClick={dismissInstructions}>Dismiss</button>
        </div>
      )}
    </div>
  );
}
