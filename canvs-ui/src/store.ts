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
  validateGraph,
} from "./api";
import type {
  Graph,
  GraphError,
  MetricEvent,
  NodeRunStatus,
  NodeSpec,
  RegistryResponse,
  RunStatus,
  RunTarget,
} from "./types";

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
  run: RunState;

  loadRegistry: () => Promise<void>;
  checkHealth: () => Promise<void>;

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

function stopPolling(set: (partial: Partial<StoreState> | ((s: StoreState) => Partial<StoreState>)) => void) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  set((s) => ({ run: { ...s.run, polling: false } }));
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

function startPolling(
  get: () => StoreState,
  set: (partial: Partial<StoreState> | ((s: StoreState) => Partial<StoreState>)) => void
) {
  stopPolling(set);
  set((s) => ({ run: { ...s.run, polling: true } }));

  pollTimer = setInterval(async () => {
    const { run } = get();
    if (!run.runId) {
      stopPolling(set);
      return;
    }
    try {
      const [metricsRes, runRes] = await Promise.all([
        getRunMetrics(run.runId, run.lastEventId).catch((e) => {
          if (e instanceof ApiError && e.status === 404) return { events: [] };
          throw e;
        }),
        getRun(run.runId),
      ]);

      set({ backendHealthy: true });

      const newEvents = metricsRes.events;
      const lastEventId = newEvents.length > 0 ? newEvents[newEvents.length - 1].id : run.lastEventId;

      set((s) => ({
        nodes: applyEventsToNodes(s.nodes, newEvents),
        run: {
          ...s.run,
          status: runRes.status,
          lastEventId,
          events: [...s.run.events, ...newEvents],
          log: runRes.log,
        },
      }));

      if (TERMINAL_STATUSES.includes(runRes.status)) {
        stopPolling(set);
      }
    } catch {
      set({ backendHealthy: false });
    }
  }, 1000);
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
  run: initialRunState,

  loadRegistry: async () => {
    const registry = await getRegistry();
    set({ registry });
  },

  checkHealth: async () => {
    try {
      const health = await getHealth();
      set({ backendHealthy: health.ok });
    } catch {
      set({ backendHealthy: false });
    }
  },

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

  newGraph: () =>
    set({
      nodes: [],
      edges: [],
      nodeIdCounter: 1,
      selectedNodeId: null,
      graphId: crypto.randomUUID(),
      graphName: "untitled",
      validationErrors: [],
      run: initialRunState,
    }),

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

    startPolling(get, set);
  },

  killActiveRun: async () => {
    const { runId } = get().run;
    if (!runId) return;
    const res = await killRun(runId);
    set((s) => ({ run: { ...s.run, status: res.status } }));
  },

  dismissInstructions: () => set((s) => ({ run: { ...s.run, showInstructions: false } })),

  resetRunView: () => set({ run: initialRunState }),
}));
