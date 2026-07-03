import { useRef, useState } from "react";
import { useStore } from "../store";
import type { Graph } from "../types";

const STORAGE_KEY = "canvs:graphs";

function readSaved(): Record<string, Graph> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function writeSaved(all: Record<string, Graph>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

export function GraphIO() {
  const graphName = useStore((s) => s.graphName);
  const toGraphJSON = useStore((s) => s.toGraphJSON);
  const loadFromGraphJSON = useStore((s) => s.loadFromGraphJSON);
  const newGraph = useStore((s) => s.newGraph);
  const registry = useStore((s) => s.registry);

  const [savedNames, setSavedNames] = useState<string[]>(() => Object.keys(readSaved()));
  const [selected, setSelected] = useState<string>("");
  const [nameDraft, setNameDraft] = useState(graphName);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSave = () => {
    const all = readSaved();
    const graph = toGraphJSON();
    graph.name = nameDraft || "untitled";
    all[graph.name] = graph;
    writeSaved(all);
    setSavedNames(Object.keys(all));
    setSelected(graph.name);
  };

  const handleLoad = () => {
    if (!selected || !registry) return;
    const all = readSaved();
    const graph = all[selected];
    if (graph) loadFromGraphJSON(graph);
  };

  const handleExport = () => {
    const graph = toGraphJSON();
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${graph.name || "graph"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = async (file: File) => {
    const text = await file.text();
    const graph = JSON.parse(text) as Graph;
    loadFromGraphJSON(graph);
    setNameDraft(graph.name);
  };

  return (
    <div className="graph-io">
      <input
        className="graph-name-input"
        value={nameDraft}
        onChange={(e) => setNameDraft(e.target.value)}
        placeholder="graph name"
      />
      <button onClick={handleSave}>Save</button>

      <select value={selected} onChange={(e) => setSelected(e.target.value)}>
        <option value="" disabled>
          saved graphs...
        </option>
        {savedNames.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      <button onClick={handleLoad} disabled={!selected}>
        Load
      </button>

      <button onClick={handleExport}>Export</button>
      <button onClick={() => fileInputRef.current?.click()}>Import</button>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleImportFile(file);
          e.target.value = "";
        }}
      />
      <button onClick={() => newGraph()}>New</button>
    </div>
  );
}
