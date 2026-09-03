-- Restrict the exposed public schema to authenticated application users.
-- This migration is intentionally repeatable so it can harden projects that
-- already ran 001/002 without changing the historical baseline migrations.

alter table public.profiles enable row level security;
alter table public.stores enable row level security;
alter table public.store_memberships enable row level security;
alter table public.strategy_configs enable row level security;
alter table public.tasks enable row level security;
alter table public.task_runs enable row level security;
alter table public.audit_events enable row level security;

revoke all privileges on table
  public.profiles,
  public.stores,
  public.store_memberships,
  public.strategy_configs,
  public.tasks,
  public.task_runs,
  public.audit_events
from public, anon, authenticated;

grant usage on schema public to authenticated;

grant select on table
  public.profiles,
  public.stores,
  public.store_memberships,
  public.strategy_configs,
  public.tasks,
  public.task_runs,
  public.audit_events
to authenticated;

grant insert (
  task_id,
  created_by,
  store_id,
  self_asin,
  competitor_asins,
  core_keywords,
  product_stage,
  strategy_id,
  task_config_override,
  input_file_path,
  input_file_hash,
  currency_code,
  status,
  current_stage
) on table public.tasks to authenticated;

create or replace function public.has_store_access(target_store uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select
    (select auth.uid()) is not null
    and exists (
      select 1
      from public.store_memberships sm
      where sm.store_id = target_store
        and sm.user_id = (select auth.uid())
    );
$$;

-- Functions are executable by PUBLIC by default. Remove that inherited path
-- before granting this policy helper only to signed-in application users.
revoke execute on function public.has_store_access(uuid) from public, anon, authenticated;
grant execute on function public.has_store_access(uuid) to authenticated;

drop policy if exists profiles_self on public.profiles;
drop policy if exists stores_member_read on public.stores;
drop policy if exists memberships_self_read on public.store_memberships;
drop policy if exists strategies_member_read on public.strategy_configs;
drop policy if exists tasks_member_read on public.tasks;
drop policy if exists tasks_member_insert on public.tasks;
drop policy if exists runs_member_read on public.task_runs;
drop policy if exists audit_member_read on public.audit_events;

create policy profiles_self
on public.profiles for select
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = user_id
);

create policy stores_member_read
on public.stores for select
to authenticated
using (
  (select auth.uid()) is not null
  and public.has_store_access(store_id)
);

create policy memberships_self_read
on public.store_memberships for select
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = user_id
);

create policy strategies_member_read
on public.strategy_configs for select
to authenticated
using (
  (select auth.uid()) is not null
  and public.has_store_access(store_id)
);

create policy tasks_member_read
on public.tasks for select
to authenticated
using (
  (select auth.uid()) is not null
  and public.has_store_access(store_id)
);

create policy tasks_member_insert
on public.tasks for insert
to authenticated
with check (
  (select auth.uid()) is not null
  and created_by = (select auth.uid())
  and public.has_store_access(store_id)
  and status = 'pending'
  and current_stage = 'ingestion'
);

create policy runs_member_read
on public.task_runs for select
to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
    from public.tasks t
    where t.task_id = task_runs.task_id
      and public.has_store_access(t.store_id)
  )
);

create policy audit_member_read
on public.audit_events for select
to authenticated
using (
  (select auth.uid()) is not null
  and (
    (store_id is not null and public.has_store_access(store_id))
    or (store_id is null and user_id = (select auth.uid()))
  )
);
