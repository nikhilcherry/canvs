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
  const readOnly = useStore((s) => s.run.readOnly);
  const showInstructions = useStore((s) => s.run.showInstructions);
  const validationErrors = useStore((s) => s.validationErrors);
  const polling = useStore((s) => s.run.polling);
  const liveMode = useStore((s) => s.run.liveMode);
  const kernelUrl = useStore((s) => s.run.kernelUrl);
  const runError = useStore((s) => s.run.runError);
  const kaggleAvailable = useStore((s) => s.kaggleAvailable);
  const kaggleUnavailableReason = useStore((s) => s.kaggleUnavailableReason);
  const kaggleConfig = useStore((s) => s.kaggleConfig);

  const validateNow = useStore((s) => s.validateNow);
  const startRun = useStore((s) => s.startRun);
  const pushToKaggle = useStore((s) => s.pushToKaggle);
  const killActiveRun = useStore((s) => s.killActiveRun);
  const dismissInstructions = useStore((s) => s.dismissInstructions);
  const updateKaggleConfig = useStore((s) => s.updateKaggleConfig);
  const setTarget = (t: RunTarget) => useStore.setState((s) => ({ run: { ...s.run, target: t } }));

  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const [showKaggleConfig, setShowKaggleConfig] = useState(false);
  const busy = !readOnly && runId !== null && (runStatus === "pending" || runStatus === "running");

  const handleValidate = async () => {
    const valid = await validateNow();
    setValidateMsg(valid ? "Graph is valid" : `${useStore.getState().validationErrors.length} error(s)`);
    setTimeout(() => setValidateMsg(null), 4000);
  };

  const handleDatasetSlugsChange = (raw: string) => {
    const slugs = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    updateKaggleConfig({ datasetSlugs: slugs });
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

      {target === "kaggle" ? (
        <>
          <button onClick={() => setShowKaggleConfig((v) => !v)} disabled={busy}>
            Kaggle settings
          </button>
          <button className="btn-primary" onClick={() => startRun(target)} disabled={busy}>
            Download
          </button>
          <button
            className="btn-primary"
            onClick={() => pushToKaggle()}
            disabled={busy || kaggleAvailable === false}
            title={kaggleAvailable === false ? (kaggleUnavailableReason ?? "Kaggle push unavailable") : undefined}
          >
            Push
          </button>
        </>
      ) : (
        <button className="btn-primary" onClick={() => startRun(target)} disabled={busy}>
          Run
        </button>
      )}

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
          {readOnly ? "history · " : null}
          {polling ? <span className={`live-indicator live-indicator-${liveMode}`}>{liveMode}</span> : null}
          {polling ? " · " : ""}
          {runStatus}
        </span>
      )}

      {kernelUrl && (
        <a className="run-bar-msg ok" href={kernelUrl} target="_blank" rel="noreferrer">
          kernel ↗
        </a>
      )}

      {runError && <span className="run-bar-msg error">{runError}</span>}

      {showKaggleConfig && target === "kaggle" && (
        <div className="kaggle-config-popover">
          <label>
            Title
            <input
              value={kaggleConfig.title}
              onChange={(e) => updateKaggleConfig({ title: e.target.value })}
            />
          </label>
          <label>
            Dataset slugs (comma-separated)
            <input
              defaultValue={kaggleConfig.datasetSlugs.join(", ")}
              onBlur={(e) => handleDatasetSlugsChange(e.target.value)}
              placeholder="username/dataset-slug"
            />
          </label>
          <label className="kaggle-config-checkbox">
            <input
              type="checkbox"
              checked={kaggleConfig.gpu}
              onChange={(e) => updateKaggleConfig({ gpu: e.target.checked })}
            />
            Enable GPU
          </label>
          {kaggleAvailable === false && (
            <span className="run-bar-msg error">Push unavailable: {kaggleUnavailableReason}</span>
          )}
        </div>
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
