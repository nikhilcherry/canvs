import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { create } from "zustand";
import {
  ApiError,
  createRun,
  getHealth,
  getRegistry,
  getRun,
  getRunMetrics,
  killRun,
  listRuns,
  validateGraph,
} from "./api";
import { subscribeToRunMetrics, type RealtimeHandle } from "./realtime";
import type {
  Graph,
  GraphError,
  MetricEvent,
  NodeRunStatus,
  NodeSpec,
  RegistryResponse,
  RunHistoryEntry,
  RunStatus,
  RunTarget,
} from "./types";

const KAGGLE_CONFIG_KEY = "canvs:kaggleConfig";

export interface KaggleConfig {
  title: string;
  datasetSlugs: string[];
  gpu: boolean;
}

function readKaggleConfig(defaultTitle: string): KaggleConfig {
  try {
    const raw = localStorage.getItem(KAGGLE_CONFIG_KEY);
    if (!raw) return { title: defaultTitle, datasetSlugs: [], gpu: false };
    const parsed = JSON.parse(raw);
    return {
      title: typeof parsed.title === "string" ? parsed.title : defaultTitle,
      datasetSlugs: Array.isArray(parsed.datasetSlugs) ? parsed.datasetSlugs : [],
      gpu: Boolean(parsed.gpu),
    };
  } catch {
    return { title: defaultTitle, datasetSlugs: [], gpu: false };
  }
}

function writeKaggleConfig(config: KaggleConfig) {
  localStorage.setItem(KAGGLE_CONFIG_KEY, JSON.stringify(config));
}

const CATEGORY_PALETTE = [
  "#6ea8fe",
  "#4ade80",
  "#fbbf24",
  "#f87171",
  "#c084fc",
  "#22d3ee",
  "#fb923c",
  "#f472b6",
];

export function hashCategoryColor(category: string): string {
  let h = 0;
  for (let i = 0; i < category.length; i++) {
    h = (h * 31 + category.charCodeAt(i)) | 0;
  }
  return CATEGORY_PALETTE[Math.abs(h) % CATEGORY_PALETTE.length];
}

export interface MetricPoint {
  step: number;
  values: Record<string, number>;
}

export interface CanvsNodeData extends Record<string, unknown> {
  spec: NodeSpec;
  config: Record<string, unknown>;
  status: NodeRunStatus;
  errors: GraphError[];
  metrics: MetricPoint[];
}

export type CanvsNode = Node<CanvsNodeData>;

const TERMINAL_STATUSES: RunStatus[] = ["done", "failed"];

interface RunState {
  runId: string | null;
  target: RunTarget;
  status: RunStatus | null;
  lastEventId: number;
  events: MetricEvent[];
  log: string[];
  polling: boolean;
  artifactContent: string | null;
  artifactFilename: string | null;
  showInstructions: boolean;
  runError: string | null;
  kernelUrl: string | null;
  liveMode: "live" | "polling";
  readOnly: boolean;
}

const initialRunState: RunState = {
  runId: null,
  target: "local",
  status: null,
  lastEventId: 0,
  events: [],
  log: [],
  polling: false,
  artifactContent: null,
  artifactFilename: null,
  showInstructions: false,
  runError: null,
  kernelUrl: null,
  liveMode: "polling",
  readOnly: false,
};

interface StoreState {
  registry: RegistryResponse | null;
  nodes: CanvsNode[];
  edges: Edge[];
  nodeIdCounter: number;
  selectedNodeId: string | null;
  graphId: string;
  graphName: string;
  validationErrors: GraphError[];
  backendHealthy: boolean | null;
  supabaseConfigured: boolean;
  kaggleAvailable: boolean | null;
  kaggleUnavailableReason: string | null;
  kaggleConfig: KaggleConfig;
  run: RunState;
  historyRuns: RunHistoryEntry[];

  loadRegistry: () => Promise<void>;
  checkHealth: () => Promise<void>;
  updateKaggleConfig: (patch: Partial<KaggleConfig>) => void;
  pushToKaggle: () => Promise<void>;
  loadHistory: () => Promise<void>;
  viewHistoryRun: (runId: string) => Promise<void>;
  restoreHistoryGraph: (runId: string) => void;

  onNodesChange: (changes: NodeChange<CanvsNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;

  addNode: (spec: NodeSpec, position: { x: number; y: number }) => void;
  updateConfig: (nodeId: string, key: string, value: unknown) => void;
  deleteNode: (nodeId: string) => void;
  deleteEdge: (edgeId: string) => void;
  selectNode: (nodeId: string | null) => void;

  newGraph: () => void;
  toGraphJSON: () => Graph;
  loadFromGraphJSON: (graph: Graph) => void;

  validateNow: () => Promise<boolean>;
  startRun: (target: RunTarget) => Promise<void>;
  killActiveRun: () => Promise<void>;
  dismissInstructions: () => void;
  resetRunView: () => void;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;
let realtimeHandle: RealtimeHandle | null = null;

type Setter = (partial: Partial<StoreState> | ((s: StoreState) => Partial<StoreState>)) => void;

function stopPolling(set: Setter) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  set((s) => ({ run: { ...s.run, polling: false } }));
}

function stopRealtime() {
  if (realtimeHandle) {
    realtimeHandle.stop();
    realtimeHandle = null;
  }
}

function mergeNewEvents(existing: MetricEvent[], incoming: MetricEvent[]): MetricEvent[] {
  const seen = new Set(existing.map((e) => e.id));
  const fresh = incoming.filter((e) => !seen.has(e.id));
  if (fresh.length === 0) return existing;
  return [...existing, ...fresh];
}

function applyEventsToNodes(nodes: CanvsNode[], events: MetricEvent[]): CanvsNode[] {
  if (events.length === 0) return nodes;
  const byId = new Map(nodes.map((n) => [n.id, n]));

  for (const ev of events) {
    if (!ev.node) continue;
    const node = byId.get(ev.node);
    if (!node) continue;

    let status: NodeRunStatus = node.data.status;
    let metrics = node.data.metrics;

    if (ev.event === "node_start") status = "running";
    else if (ev.event === "node_done") status = "done";
    else if (ev.event === "node_failed") status = "failed";
    else if (ev.event === "metric" && ev.values) {
      const point: MetricPoint = { step: ev.step ?? 0, values: ev.values };
      metrics = [...metrics, point].slice(-50);
    }

    if (status !== node.data.status || metrics !== node.data.metrics) {
      byId.set(ev.node, { ...node, data: { ...node.data, status, metrics } });
    }
  }

  return nodes.map((n) => byId.get(n.id) ?? n);
}

async function pollOnce(get: () => StoreState, set: Setter): Promise<boolean> {
  const { run } = get();
  if (!run.runId) return true;

  try {
    const [metricsRes, runRes] = await Promise.all([
      getRunMetrics(run.runId, run.lastEventId).catch((e) => {
        if (e instanceof ApiError && e.status === 404) return { events: [] };
        throw e;
      }),
      getRun(run.runId),
    ]);

    set({ backendHealthy: true });

    set((s) => {
      const events = mergeNewEvents(s.run.events, metricsRes.events);
      const lastEventId = events.length > 0 ? Math.max(...events.map((e) => e.id)) : s.run.lastEventId;
      return {
        nodes: applyEventsToNodes(s.nodes, metricsRes.events),
        run: { ...s.run, status: runRes.status, lastEventId, events, log: runRes.log },
      };
    });

    return TERMINAL_STATUSES.includes(runRes.status);
  } catch {
    set({ backendHealthy: false });
    return false;
  }
}

function beginPolling(get: () => StoreState, set: Setter, intervalMs: number) {
  if (pollTimer) clearInterval(pollTimer);
  set((s) => ({ run: { ...s.run, polling: true } }));

  pollTimer = setInterval(async () => {
    const terminal = await pollOnce(get, set);
    if (terminal) {
      stopPolling(set);
      stopRealtime();
    }
  }, intervalMs);
}

function handleRealtimeEvent(set: Setter, ev: MetricEvent) {
  set((s) => {
    const events = mergeNewEvents(s.run.events, [ev]);
    if (events === s.run.events) return {};
    const lastEventId = Math.max(s.run.lastEventId, ev.id);
    return {
      nodes: applyEventsToNodes(s.nodes, [ev]),
      run: { ...s.run, events, lastEventId },
    };
  });
}

// Prefers a live Supabase realtime channel (with a slow 10s poll as a
// gap-filler, since realtime can drop events across a reconnect) and
// falls back to the original 1s poll whenever Supabase isn't
// configured or the channel fails to open or later errors out.
async function startMetricsStream(get: () => StoreState, set: Setter) {
  stopPolling(set);
  stopRealtime();

  const { run, supabaseConfigured } = get();
  const runId = run.runId;
  if (!runId) return;

  if (supabaseConfigured) {
    const handle = await subscribeToRunMetrics(
      runId,
      (ev) => handleRealtimeEvent(set, ev),
      () => {
        stopRealtime();
        set((s) => ({ run: { ...s.run, liveMode: "polling" } }));
        beginPolling(get, set, 1000);
      }
    );
    if (handle && get().run.runId === runId) {
      realtimeHandle = handle;
      set((s) => ({ run: { ...s.run, liveMode: "live" } }));
      beginPolling(get, set, 10000);
      return;
    }
    if (handle) handle.stop(); // run changed while we were connecting
  }

  set((s) => ({ run: { ...s.run, liveMode: "polling" } }));
  beginPolling(get, set, 1000);
}

export const useStore = create<StoreState>((set, get) => ({
  registry: null,
  nodes: [],
  edges: [],
  nodeIdCounter: 1,
  selectedNodeId: null,
  graphId: crypto.randomUUID(),
  graphName: "untitled",
  validationErrors: [],
  backendHealthy: null,
  supabaseConfigured: false,
  kaggleAvailable: null,
  kaggleUnavailableReason: null,
  kaggleConfig: readKaggleConfig("untitled"),
  run: initialRunState,
  historyRuns: [],

  loadRegistry: async () => {
    const registry = await getRegistry();
    set({ registry });
  },

  checkHealth: async () => {
    try {
      const health = await getHealth();
      set({
        backendHealthy: health.ok,
        supabaseConfigured: health.supabase,
        kaggleAvailable: health.kaggle.available,
        kaggleUnavailableReason: health.kaggle.reason,
      });
    } catch {
      set({ backendHealthy: false });
    }
  },

  updateKaggleConfig: (patch) =>
    set((s) => {
      const next = { ...s.kaggleConfig, ...patch };
      writeKaggleConfig(next);
      return { kaggleConfig: next };
    }),

  onNodesChange: (changes) => set((s) => ({ nodes: applyNodeChanges<CanvsNode>(changes, s.nodes) })),

  onEdgesChange: (changes) => set((s) => ({ edges: applyEdgeChanges(changes, s.edges) })),

  onConnect: (connection) =>
    set((s) => ({
      edges: addEdge(
        { ...connection, id: `e${connection.source}-${connection.target}-${connection.targetHandle}` },
        s.edges
      ),
    })),

  addNode: (spec, position) =>
    set((s) => {
      const id = `n${s.nodeIdCounter}`;
      const config: Record<string, unknown> = {};
      for (const [key, schema] of Object.entries(spec.params)) {
        if (schema.default !== undefined) config[key] = schema.default;
      }
      const node: CanvsNode = {
        id,
        type: "canvs",
        position,
        data: { spec, config, status: "idle", errors: [], metrics: [] },
      };
      return { nodes: [...s.nodes, node], nodeIdCounter: s.nodeIdCounter + 1 };
    }),

  updateConfig: (nodeId, key, value) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, config: { ...n.data.config, [key]: value } } } : n
      ),
    })),

  deleteNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
    })),

  deleteEdge: (edgeId) => set((s) => ({ edges: s.edges.filter((e) => e.id !== edgeId) })),

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  newGraph: () => {
    stopPolling(set);
    stopRealtime();
    set({
      nodes: [],
      edges: [],
      nodeIdCounter: 1,
      selectedNodeId: null,
      graphId: crypto.randomUUID(),
      graphName: "untitled",
      validationErrors: [],
      run: initialRunState,
    });
  },

  toGraphJSON: () => {
    const { nodes, edges, graphId, graphName } = get();
    return {
      graph_id: graphId,
      name: graphName,
      nodes: nodes.map((n) => ({ id: n.id, spec: n.data.spec.id, config: n.data.config })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
        target_port: e.targetHandle ?? "",
      })),
      ui: {
        positions: Object.fromEntries(nodes.map((n) => [n.id, { x: n.position.x, y: n.position.y }])),
      },
    };
  },

  loadFromGraphJSON: (graph) => {
    const { registry } = get();
    if (!registry) return;
    const specById = new Map(registry.nodes.map((s) => [s.id, s]));

    const positions = graph.ui?.positions ?? {};
    let maxCounter = 0;
    const nodes: CanvsNode[] = graph.nodes.map((gn, i) => {
      const match = /^n(\d+)$/.exec(gn.id);
      if (match) maxCounter = Math.max(maxCounter, parseInt(match[1], 10));
      const spec = specById.get(gn.spec);
      const pos = positions[gn.id] ?? { x: 100 + (i % 5) * 220, y: 100 + Math.floor(i / 5) * 160 };
      return {
        id: gn.id,
        type: "canvs",
        position: pos,
        data: {
          spec: spec ?? {
            id: gn.spec,
            category: "unknown",
            name: gn.spec,
            description: "",
            params: {},
            inputs: [],
            input_defaults: {},
            outputs: [],
            source: "",
            requires: [],
            accepts_run_id: false,
            accepts_node_id: false,
          },
          config: gn.config,
          status: "idle",
          errors: [],
          metrics: [],
        },
      };
    });

    const edges: Edge[] = graph.edges.map((ge) => ({
      id: `e${ge.source}-${ge.target}-${ge.target_port}`,
      source: ge.source,
      target: ge.target,
      sourceHandle: "output",
      targetHandle: ge.target_port,
    }));

    stopPolling(set);
    stopRealtime();
    set({
      nodes,
      edges,
      nodeIdCounter: maxCounter + 1,
      graphId: graph.graph_id,
      graphName: graph.name,
      selectedNodeId: null,
      validationErrors: [],
      run: initialRunState,
    });
  },

  validateNow: async () => {
    const graph = get().toGraphJSON();
    const res = await validateGraph(graph);
    set((s) => ({
      validationErrors: res.errors,
      nodes: s.nodes.map((n) => ({
        ...n,
        data: { ...n.data, errors: res.errors.filter((e) => e.node_id === n.id) },
      })),
    }));
    return res.valid;
  },

  startRun: async (target) => {
    const valid = await get().validateNow();
    if (!valid) return;

    set((s) => ({
      run: { ...initialRunState, target },
      nodes: s.nodes.map((n) => ({ ...n, data: { ...n.data, status: "idle", metrics: [] } })),
    }));

    const graph = get().toGraphJSON();
    const result = await createRun(graph, target);
    if (!result.ok) {
      set((s) => ({
        validationErrors: result.errors.errors,
        nodes: s.nodes.map((n) => ({
          ...n,
          data: { ...n.data, errors: result.errors.errors.filter((e) => e.node_id === n.id) },
        })),
      }));
      return;
    }

    const { data } = result;
    set((s) => ({
      run: {
        ...s.run,
        runId: data.run_id,
        status: data.status,
        artifactContent: data.artifact_content ?? null,
        artifactFilename: data.artifact_filename,
        showInstructions: target !== "local",
      },
    }));

    if (target !== "local" && data.artifact_content) {
      const blob = new Blob([data.artifact_content], { type: "application/x-ipynb+json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.artifact_filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    await startMetricsStream(get, set);
  },

  pushToKaggle: async () => {
    const valid = await get().validateNow();
    if (!valid) return;

    set((s) => ({
      run: { ...initialRunState, target: "kaggle" },
      nodes: s.nodes.map((n) => ({ ...n, data: { ...n.data, status: "idle", metrics: [] } })),
    }));

    const graph = get().toGraphJSON();
    const { kaggleConfig } = get();
    const result = await createRun(graph, "kaggle", {
      push: true,
      title: kaggleConfig.title,
      dataset_slugs: kaggleConfig.datasetSlugs,
      gpu: kaggleConfig.gpu,
    });
    if (!result.ok) {
      set((s) => ({
        validationErrors: result.errors.errors,
        nodes: s.nodes.map((n) => ({
          ...n,
          data: { ...n.data, errors: result.errors.errors.filter((e) => e.node_id === n.id) },
        })),
      }));
      return;
    }

    const { data } = result;
    set((s) => ({
      run: {
        ...s.run,
        runId: data.run_id,
        status: data.status,
        kernelUrl: data.kernel_url ?? null,
        artifactContent: data.artifact_content ?? null,
        artifactFilename: data.artifact_filename,
        runError:
          data.push_available === false
            ? (data.push_unavailable_reason ?? "Kaggle push unavailable")
            : null,
      },
    }));

    if (data.status === "pushed") {
      await startMetricsStream(get, set);
    }
  },

  killActiveRun: async () => {
    const { runId } = get().run;
    if (!runId) return;
    const res = await killRun(runId);
    set((s) => ({ run: { ...s.run, status: res.status } }));
  },

  dismissInstructions: () => set((s) => ({ run: { ...s.run, showInstructions: false } })),

  resetRunView: () => {
    stopPolling(set);
    stopRealtime();
    set({ run: initialRunState });
  },

  loadHistory: async () => {
    const res = await listRuns();
    set({ historyRuns: res.runs });
  },

  viewHistoryRun: async (runId) => {
    stopPolling(set);
    stopRealtime();

    const entry = get().historyRuns.find((r) => r.run_id === runId);
    const metricsRes = await getRunMetrics(runId, 0);
    const events = metricsRes.events;
    const lastEventId = events.length > 0 ? Math.max(...events.map((e) => e.id)) : 0;

    set((s) => ({
      selectedNodeId: null,
      run: {
        ...initialRunState,
        runId,
        target: entry?.target ?? "local",
        status: entry?.status ?? null,
        events,
        lastEventId,
        readOnly: true,
      },
      nodes: applyEventsToNodes(
        s.nodes.map((n) => ({ ...n, data: { ...n.data, status: "idle" as const, metrics: [] } })),
        events
      ),
    }));
  },

  restoreHistoryGraph: (runId) => {
    const entry = get().historyRuns.find((r) => r.run_id === runId);
    if (!entry) return;

    const hasExistingWork = get().nodes.length > 0;
    if (hasExistingWork && !window.confirm("Restore this run's graph? Unsaved canvas changes will be lost.")) {
      return;
    }

    get().loadFromGraphJSON(entry.graph);
  },
}));
