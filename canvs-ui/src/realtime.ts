// Supabase realtime channel for a single run's metrics. Falls back to
// null (caller keeps polling) whenever Supabase isn't configured or the
// channel can't be opened -- this module never throws.
import { createClient, type RealtimeChannel, type SupabaseClient } from "@supabase/supabase-js";
import type { MetricEvent } from "./types";

interface SupabaseConfig {
  supabase_url: string;
  supabase_anon_key: string;
}

let cachedClient: SupabaseClient | null = null;
let cachedConfig: SupabaseConfig | null = null;

async function getConfig(): Promise<SupabaseConfig | null> {
  if (cachedConfig) return cachedConfig;
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return null;
    cachedConfig = (await res.json()) as SupabaseConfig;
    return cachedConfig;
  } catch {
    return null;
  }
}

async function getClient(): Promise<SupabaseClient | null> {
  if (cachedClient) return cachedClient;
  const config = await getConfig();
  if (!config) return null;
  cachedClient = createClient(config.supabase_url, config.supabase_anon_key);
  return cachedClient;
}

export interface RealtimeHandle {
  stop: () => void;
}

interface MetricsRow {
  id: number;
  event: MetricEvent["event"];
  node: string | null;
  step: number | null;
  values: Record<string, number> | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

function rowToEvent(row: MetricsRow): MetricEvent {
  return {
    id: row.id,
    event: row.event,
    node: row.node,
    step: row.step,
    values: row.values,
    payload: row.payload,
    created_at: row.created_at ? Date.parse(row.created_at) / 1000 : 0,
  };
}

/**
 * Subscribe to INSERT events on `metrics` for one run_id. Returns null
 * (rather than throwing) if Supabase isn't configured or the channel
 * fails to open, so callers can fall back to polling unconditionally.
 */
export async function subscribeToRunMetrics(
  runId: string,
  onEvent: (event: MetricEvent) => void,
  onDisconnect: () => void
): Promise<RealtimeHandle | null> {
  const client = await getClient();
  if (!client) return null;

  let settled = false;
  return new Promise((resolve) => {
    const channel: RealtimeChannel = client
      .channel(`metrics:${runId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "metrics", filter: `run_id=eq.${runId}` },
        (payload) => onEvent(rowToEvent(payload.new as MetricsRow))
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED" && !settled) {
          settled = true;
          resolve({ stop: () => channel.unsubscribe() });
        } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
          if (!settled) {
            settled = true;
            resolve(null);
          } else {
            onDisconnect();
          }
        }
      });
  });
}
