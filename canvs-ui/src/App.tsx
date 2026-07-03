import { useEffect } from "react";
import { Canvas } from "./components/Canvas";
import { GraphIO } from "./components/GraphIO";
import { Inspector } from "./components/Inspector";
import { RunBar } from "./components/RunBar";
import { Sidebar } from "./components/Sidebar";
import { useStore } from "./store";

export function App() {
  const loadRegistry = useStore((s) => s.loadRegistry);
  const checkHealth = useStore((s) => s.checkHealth);
  const backendHealthy = useStore((s) => s.backendHealthy);

  useEffect(() => {
    checkHealth();
    loadRegistry().catch(() => {});
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, [checkHealth, loadRegistry]);

  return (
    <div className="app">
      {backendHealthy === false && (
        <div className="backend-down-banner">Backend unreachable — retrying...</div>
      )}
      <div className="top-bar">
        <span className="app-title">canvs</span>
        <GraphIO />
        <RunBar />
      </div>
      <div className="main-layout">
        <Sidebar />
        <Canvas />
        <div className="inspector-panel">
          <Inspector />
        </div>
      </div>
    </div>
  );
}
