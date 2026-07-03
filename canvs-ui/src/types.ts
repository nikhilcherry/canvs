// Mirrors the pydantic models in src/canvs/{registry,graph,server}.py.
// Keep in lockstep with the backend — this is the only place types are defined.

export type ParamType = "string" | "integer" | "number" | "boolean";

export interface ParamSchema {
  type: ParamType;
  enum?: string[];
  default?: string | number | boolean;
  required?: boolean;
}

export interface NodeSpec {
  id: string;
  category: string;
  name: string;
  description: string;
  params: Record<string, ParamSchema>;
  inputs: string[];
  input_defaults: Record<string, unknown>;
  outputs: string[];
  source: string;
  requires: string[];
  accepts_run_id: boolean;
  accepts_node_id: boolean;
}

export interface RegistryResponse {
  categories: string[];
  nodes: NodeSpec[];
}

export interface GraphNode {
  id: string;
  spec: string;
  config: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  target_port: string;
}

export interface GraphUiPosition {
  x: number;
  y: number;
}

export interface GraphUi {
  positions: Record<string, GraphUiPosition>;
}

export interface Graph {
  graph_id: string;
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  // Frontend-only. The backend ignores unknown fields (pydantic extra="ignore")
  // but we still round-trip it through save/load so layout survives a reload.
  ui?: GraphUi;
}

export interface GraphError {
  node_id: string | null;
  field: string;
  message: string;
}

export interface ValidateResponse {
  valid: boolean;
  errors: GraphError[];
}

export type RunTarget = "local" | "kaggle" | "colab";

export type RunStatus = "pending" | "running" | "compiled" | "pushed" | "done" | "failed";

export interface KaggleRunOptions {
  push: boolean;
  title: string;
  dataset_slugs: string[];
  gpu: boolean;
}

export interface CreateRunResponse {
  run_id: string;
  status: RunStatus;
  artifact_filename: string;
  artifact_content?: string;
  kernel_url?: string;
  push_available?: boolean;
  push_unavailable_reason?: string;
}

export interface RunDetailResponse {
  run_id: string;
  status: RunStatus;
  log: string[];
  kernel_slug?: string;
}

export interface KillRunResponse {
  run_id: string;
  status: RunStatus;
}

export type MetricEventType =
  | "run_start"
  | "run_done"
  | "run_failed"
  | "node_start"
  | "node_done"
  | "node_failed"
  | "metric";

export interface MetricEvent {
  id: number;
  event: MetricEventType;
  node: string | null;
  step: number | null;
  values: Record<string, number> | null;
  payload: Record<string, unknown> | null;
  created_at: number;
}

export interface MetricsResponse {
  events: MetricEvent[];
}

export interface HealthResponse {
  ok: boolean;
  supabase: boolean;
  kaggle: { available: boolean; reason: string | null };
}

export type NodeRunStatus = "idle" | "running" | "done" | "failed";

export interface RunHistoryEntry {
  run_id: string;
  name: string;
  target: RunTarget;
  status: RunStatus;
  created_at: string;
  graph: Graph;
}

export interface RunHistoryResponse {
  runs: RunHistoryEntry[];
}
