-- canvs metrics channel schema.
-- Apply manually via the Supabase SQL editor or `supabase db push`.
-- RLS is deliberately deferred (internal tool, session 1 scope).

create table runs (
  run_id text primary key,
  name text,
  target text,
  status text default 'pending',   -- pending|running|done|failed
  graph jsonb,
  created_at timestamptz default now()
);

create table metrics (
  id bigint generated always as identity primary key,
  run_id text references runs(run_id),
  event text not null,
  node text,
  step int,
  values jsonb,
  payload jsonb,
  created_at timestamptz default now()
);
