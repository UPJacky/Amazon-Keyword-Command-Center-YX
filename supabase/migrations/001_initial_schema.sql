-- V1 baseline schema. Run only after reviewing in a disposable Supabase project.
create extension if not exists pgcrypto;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role text not null default 'user' check (role in ('admin', 'user')),
  created_at timestamptz not null default now()
);

create table if not exists public.stores (
  store_id uuid primary key default gen_random_uuid(),
  name text not null,
  marketplace text not null default 'US',
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists public.store_memberships (
  store_id uuid not null references public.stores(store_id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'user' check (role in ('admin', 'user')),
  created_at timestamptz not null default now(),
  primary key (store_id, user_id)
);

create table if not exists public.strategy_configs (
  config_id uuid primary key default gen_random_uuid(),
  store_id uuid references public.stores(store_id) on delete cascade,
  asin text,
  product_stage text,
  config_version text not null,
  rule_version text not null,
  config jsonb not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists public.tasks (
  task_id uuid primary key,
  created_by uuid not null references auth.users(id),
  store_id uuid not null references public.stores(store_id),
  self_asin text not null,
  competitor_asins jsonb not null default '[]'::jsonb,
  core_keywords jsonb not null default '[]'::jsonb,
  product_stage text not null,
  strategy_id uuid references public.strategy_configs(config_id),
  task_config_override jsonb not null default '{}'::jsonb,
  input_file_path text not null,
  input_file_hash text not null,
  currency_code text,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  current_stage text not null default 'ingestion',
  failure_reason jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.task_runs (
  run_id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(task_id) on delete cascade,
  previous_run_id uuid references public.task_runs(run_id),
  rule_version text,
  config_version text,
  provider_snapshot_version text,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  report_path text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create table if not exists public.audit_events (
  event_id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id),
  store_id uuid references public.stores(store_id),
  task_id uuid references public.tasks(task_id),
  run_id uuid references public.task_runs(run_id),
  event_type text not null,
  result text not null default 'success',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function public.has_store_access(target_store uuid)
returns boolean language sql stable security definer set search_path = public
as $$ select exists (select 1 from public.store_memberships where store_id = target_store and user_id = auth.uid()); $$;

alter table public.profiles enable row level security;
alter table public.stores enable row level security;
alter table public.store_memberships enable row level security;
alter table public.strategy_configs enable row level security;
alter table public.tasks enable row level security;
alter table public.task_runs enable row level security;
alter table public.audit_events enable row level security;

create policy profiles_self on public.profiles for select using (user_id = auth.uid());
create policy stores_member_read on public.stores for select using (public.has_store_access(store_id));
create policy memberships_self_read on public.store_memberships for select using (user_id = auth.uid());
create policy strategies_member_read on public.strategy_configs for select using (public.has_store_access(store_id));
create policy tasks_member_read on public.tasks for select using (public.has_store_access(store_id));
create policy tasks_member_insert on public.tasks for insert with check (created_by = auth.uid() and public.has_store_access(store_id));
create policy runs_member_read on public.task_runs for select using (exists (select 1 from public.tasks t where t.task_id = task_runs.task_id and public.has_store_access(t.store_id)));
create policy audit_member_read on public.audit_events for select using (store_id is null or public.has_store_access(store_id));

