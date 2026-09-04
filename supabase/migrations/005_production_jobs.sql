-- LOCAL REVIEW ONLY. Requires 001-004 and Supabase Storage; not applied here.
-- Repeatable DDL in one transaction. Existing reports_member_read is untouched.
begin;

alter table public.tasks add column if not exists input_size bigint
  check (input_size > 0 and input_size <= 10485760);
-- Keep caller intent distinct from the resolved immutable strategy selection:
-- a replay with omitted strategy must not reselect newly appended configs.
alter table public.tasks add column if not exists requested_strategy_id uuid
  references public.strategy_configs(config_id);
alter table public.task_runs add column if not exists lease_token uuid;
alter table public.task_runs add column if not exists worker_id text;
alter table public.task_runs add column if not exists lease_until timestamptz;
alter table public.task_runs add column if not exists failure_reason jsonb;
alter table public.task_runs add column if not exists strategy_id uuid
  references public.strategy_configs(config_id);

-- Operational lease credentials are Worker-only even for store members.
revoke select on table public.task_runs from authenticated;
grant select (run_id, task_id, previous_run_id, rule_version, config_version,
  provider_snapshot_version, status, report_path, created_at, started_at,
  completed_at, failure_reason, strategy_id) on public.task_runs to authenticated;

-- Abort on legacy concurrent active runs; never delete or rewrite history.
create unique index if not exists kwcc_one_active_run_per_task
  on public.task_runs(task_id) where status in ('pending', 'processing');
create unique index if not exists kwcc_one_successor_per_run
  on public.task_runs(previous_run_id) where previous_run_id is not null;
create index if not exists kwcc_runs_claim_queue
  on public.task_runs(created_at, run_id) where status = 'pending';
create index if not exists kwcc_runs_expiring
  on public.task_runs(lease_until) where status = 'processing';

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('inputs', 'inputs', false, 10485760, array[
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/csv', 'application/csv', 'application/vnd.ms-excel',
  'application/octet-stream'
])
on conflict (id) do update set public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- The permissive policy opens only create. The restrictive INSERT policy also
-- constrains other permissive policies, without touching report SELECT access.
drop policy if exists kwcc_inputs_insert on storage.objects;
create policy kwcc_inputs_insert on storage.objects for insert to authenticated
with check (bucket_id = 'inputs');

drop policy if exists kwcc_objects_insert_guard on storage.objects;
create policy kwcc_objects_insert_guard on storage.objects as restrictive
for insert to authenticated with check (
  bucket_id <> 'reports' and (bucket_id <> 'inputs' or (
    (select auth.uid()) is not null
    and owner_id = (select auth.uid())::text
    and name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/input\.(xlsx|csv)$'
    and split_part(name, '/', 2) = (select auth.uid())::text
    and exists (select 1 from public.store_memberships sm
      where sm.store_id::text = split_part(name, '/', 1)
        and sm.user_id = (select auth.uid())
        and public.has_store_access(sm.store_id))
  ))
);
drop policy if exists kwcc_objects_anon_insert_guard on storage.objects;
create policy kwcc_objects_anon_insert_guard on storage.objects as restrictive
for insert to anon with check (bucket_id not in ('inputs', 'reports'));
drop policy if exists kwcc_objects_update_guard on storage.objects;
create policy kwcc_objects_update_guard on storage.objects as restrictive
for update to anon, authenticated
using (bucket_id not in ('inputs', 'reports'))
with check (bucket_id not in ('inputs', 'reports'));
drop policy if exists kwcc_objects_delete_guard on storage.objects;
create policy kwcc_objects_delete_guard on storage.objects as restrictive
for delete to anon, authenticated using (bucket_id not in ('inputs', 'reports'));

-- 003 granted COLUMN INSERT. Both table and column ACLs must be revoked.
revoke insert on table public.tasks from public, anon, authenticated;
revoke insert (task_id, created_by, store_id, self_asin, competitor_asins,
  core_keywords, product_stage, strategy_id, task_config_override,
  input_file_path, input_file_hash, currency_code, status, current_stage)
  on table public.tasks from public, anon, authenticated;

create or replace function public.kwcc_submit_task(
  p_task_id uuid, p_run_id uuid, p_store_id uuid, p_self_asin text,
  p_product_stage text, p_input_file_path text, p_input_file_hash text,
  p_input_size bigint, p_strategy_id uuid default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_task public.tasks%rowtype;
  v_run public.task_runs%rowtype;
  v_prefix text;
  v_size text;
  v_strategy_id uuid := p_strategy_id;
begin
  if v_uid is null or p_store_id is null
     or not public.has_store_access(p_store_id) then
    raise exception using errcode = '42501', message = 'STORE_ACCESS_DENIED';
  end if;
  if p_task_id is null or p_run_id is null
     or p_self_asin is null or p_self_asin !~ '^B0[A-Z0-9]{8}$'
     or p_product_stage is null
     or p_product_stage not in ('new', 'growth', 'stable', 'clearance', 'seasonal_restart')
     or p_input_file_hash is null or p_input_file_hash !~ '^[0-9a-f]{64}$'
     or p_input_size is null or p_input_size < 1 or p_input_size > 10485760 then
    raise exception using errcode = '22023', message = 'INPUT_INVALID';
  end if;
  v_prefix := p_store_id::text || '/' || v_uid::text || '/' || p_task_id::text || '/input.';
  if p_input_file_path is null
     or p_input_file_path not in (v_prefix || 'xlsx', v_prefix || 'csv') then
    raise exception using errcode = '22023', message = 'INPUT_PATH_INVALID';
  end if;
  -- Serialize identical task IDs even before a task row exists. PKs also fence
  -- run IDs reused for other tasks; unique violations become a safe conflict.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_task_id::text, 0));
  select * into v_task from public.tasks where task_id = p_task_id for update;
  if found then
    select * into v_run from public.task_runs
      where run_id = p_run_id and task_id = p_task_id and previous_run_id is null;
    if not found or v_task.created_by is distinct from v_uid
       or v_task.store_id is distinct from p_store_id
       or v_task.self_asin is distinct from p_self_asin
       or v_task.product_stage is distinct from p_product_stage
       or v_task.input_file_path is distinct from p_input_file_path
       or v_task.input_file_hash is distinct from p_input_file_hash
       or v_task.input_size is distinct from p_input_size
       or v_task.requested_strategy_id is distinct from p_strategy_id then
      raise exception using errcode = '23505', message = 'JOB_ID_CONFLICT';
    end if;
    return jsonb_build_object('task_id', v_task.task_id, 'run_id', v_run.run_id, 'status', 'pending');
  end if;
  if p_strategy_id is not null and not exists (
    select 1 from public.strategy_configs s where s.config_id = p_strategy_id
      and s.store_id = p_store_id
      and (s.asin is null or s.asin = p_self_asin)
      and (s.product_stage is null or s.product_stage = p_product_stage)
  ) then
    raise exception using errcode = '42501', message = 'STRATEGY_ACCESS_DENIED';
  end if;
  if p_strategy_id is null then
    select s.config_id into v_strategy_id from public.strategy_configs s
      where s.store_id = p_store_id and s.product_stage = p_product_stage
        and (s.asin = p_self_asin or s.asin is null)
      order by (s.asin = p_self_asin) desc nulls last,
        s.created_at desc, s.config_id desc limit 1;
  end if;
  -- Storage metadata is an admission check, NOT a content digest. Worker must
  -- download, enforce byte length and recompute SHA-256 before any Provider call.
  select o.metadata ->> 'size' into v_size from storage.objects o
    join storage.buckets b on b.id = o.bucket_id
    where o.bucket_id = 'inputs' and b.public = false
      and o.name = p_input_file_path and o.owner_id = v_uid::text
    for share of o;
  if not found or v_size is null or v_size !~ '^[0-9]{1,8}$' then
    raise exception using errcode = '22023', message = 'INPUT_OBJECT_INVALID';
  end if;
  if v_size::bigint <> p_input_size then
    raise exception using errcode = '22023', message = 'INPUT_SIZE_MISMATCH';
  end if;
  insert into public.tasks(task_id, created_by, store_id, self_asin, product_stage,
    strategy_id, requested_strategy_id, input_file_path, input_file_hash, input_size, status, current_stage)
  values (p_task_id, v_uid, p_store_id, p_self_asin, p_product_stage,
    v_strategy_id, p_strategy_id, p_input_file_path, p_input_file_hash, p_input_size, 'pending', 'ingestion');
  insert into public.task_runs(run_id, task_id, strategy_id, status)
    values (p_run_id, p_task_id, v_strategy_id, 'pending');
  insert into public.audit_events(user_id, store_id, task_id, run_id, event_type)
    values (v_uid, p_store_id, p_task_id, p_run_id, 'task_submitted');
  return jsonb_build_object('task_id', p_task_id, 'run_id', p_run_id, 'status', 'pending');
exception when unique_violation then
  raise exception using errcode = '23505', message = 'JOB_ID_CONFLICT';
end;
$$;

create or replace function public.kwcc_claim_run(
  p_worker_id text, p_lease_seconds int default 300
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_expired record;
  v_task public.tasks%rowtype;
  v_run public.task_runs%rowtype;
  v_config jsonb;
  v_now timestamptz;
  v_reason jsonb := '{"code":"LEASE_EXPIRED","stage":"worker","retryable":false}'::jsonb;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;
  if p_worker_id is null or p_worker_id !~ '^[A-Za-z0-9_.:-]{1,128}$'
     or p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 3600 then
    raise exception using errcode = '22023', message = 'LEASE_INPUT_INVALID';
  end if;
  -- Lock task then run throughout claim/finish/rerun. Never requeue expired work:
  -- a Provider may already have accepted a request before the Worker died.
  for v_expired in
    select t.task_id, t.store_id, r.run_id from public.tasks t
      join public.task_runs r on r.task_id = t.task_id
      where r.status = 'processing'
        and (r.lease_until is null or r.lease_until <= clock_timestamp())
      order by r.lease_until nulls first, r.run_id
      for update of t, r skip locked
  loop
    v_now := clock_timestamp();
    update public.task_runs set status = 'failed', completed_at = v_now,
      failure_reason = v_reason, lease_until = null
      where run_id = v_expired.run_id;
    update public.tasks set status = 'failed', current_stage = 'worker',
      completed_at = v_now, failure_reason = v_reason where task_id = v_expired.task_id;
    insert into public.audit_events(store_id, task_id, run_id, event_type, result, metadata)
      values (v_expired.store_id, v_expired.task_id, v_expired.run_id,
        'run_lease_expired', 'failed', v_reason);
  end loop;
  select r.* into v_run from public.tasks t
    join public.task_runs r on r.task_id = t.task_id
    where t.status = 'pending' and r.status = 'pending'
    order by r.created_at, r.run_id limit 1 for update of t, r skip locked;
  if not found then return null; end if;
  v_now := clock_timestamp();
  update public.task_runs set status = 'processing', started_at = v_now,
    lease_token = gen_random_uuid(), worker_id = p_worker_id,
    lease_until = v_now + make_interval(secs => p_lease_seconds)
    where run_id = v_run.run_id returning * into v_run;
  update public.tasks set status = 'processing', current_stage = 'ingestion',
    failure_reason = null, completed_at = null
    where task_id = v_run.task_id returning * into v_task;
  if v_run.strategy_id is not null then
    select s.config into v_config from public.strategy_configs s
      where s.config_id = v_run.strategy_id and s.store_id = v_task.store_id;
  end if;
  insert into public.audit_events(store_id, task_id, run_id, event_type)
    values (v_task.store_id, v_task.task_id, v_run.run_id, 'run_claimed');
  return jsonb_build_object('task', to_jsonb(v_task) || jsonb_build_object(
    'marketplace', (select s.marketplace from public.stores s where s.store_id = v_task.store_id)),
    'run', to_jsonb(v_run), 'config', v_config);
end;
$$;

create or replace function public.kwcc_heartbeat_run(
  p_run_id uuid, p_lease_token uuid, p_lease_seconds int default 300
) returns boolean language plpgsql security definer set search_path = '' as $$
declare
  v_run public.task_runs%rowtype;
  v_now timestamptz;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;
  if p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 3600 then
    raise exception using errcode = '22023', message = 'LEASE_INPUT_INVALID';
  end if;
  select * into v_run from public.task_runs where run_id = p_run_id for update;
  if not found then return false; end if;
  v_now := clock_timestamp();
  if p_lease_token is null or v_run.lease_token is distinct from p_lease_token
     or v_run.status <> 'processing' or v_run.lease_until is null
     or v_run.lease_until <= v_now then return false; end if;
  update public.task_runs set lease_until = greatest(lease_until,
    v_now + make_interval(secs => p_lease_seconds))
    where run_id = p_run_id and lease_token = p_lease_token
      and status = 'processing' and lease_until > v_now;
  return found;
end;
$$;

create or replace function public.kwcc_finish_run(
  p_run_id uuid, p_lease_token uuid, p_status text,
  p_report_path text default null, p_rule_version text default null,
  p_config_version text default null, p_provider_snapshot_version text default null,
  p_failure_reason jsonb default null
) returns boolean language plpgsql security definer set search_path = '' as $$
declare
  v_task public.tasks%rowtype;
  v_run public.task_runs%rowtype;
  v_now timestamptz;
  v_reason jsonb;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;
  select t.* into v_task from public.tasks t
    join public.task_runs r on r.task_id = t.task_id
    where r.run_id = p_run_id for update of t;
  if not found then return false; end if;
  select * into v_run from public.task_runs where run_id = p_run_id for update;
  v_now := clock_timestamp();
  if p_lease_token is null or v_run.lease_token is distinct from p_lease_token
     or v_run.status <> 'processing' or v_run.lease_until is null
     or v_run.lease_until <= v_now then return false; end if;
  if p_status is null or p_status not in ('completed', 'failed') then
    raise exception using errcode = '22023', message = 'FINISH_STATUS_INVALID';
  end if;
  if (p_rule_version is not null and p_rule_version !~ '^[A-Za-z0-9_.:-]{1,128}$')
     or (p_config_version is not null and p_config_version !~ '^[A-Za-z0-9_.:-]{1,128}$')
     or (p_provider_snapshot_version is not null and p_provider_snapshot_version !~ '^[A-Za-z0-9_.:-]{1,128}$') then
    raise exception using errcode = '22023', message = 'VERSION_INVALID';
  end if;
  if p_status = 'completed' then
    if p_failure_reason is not null or p_report_path is null
       or p_report_path !~ ('^' || v_task.task_id::text || '/' || p_run_id::text || '/report-[0-9a-f]{48}\.json$') then
      raise exception using errcode = '22023', message = 'REPORT_PATH_INVALID';
    end if;
    perform 1 from storage.objects o join storage.buckets b on b.id = o.bucket_id
      where o.bucket_id = 'reports' and b.public = false and o.name = p_report_path
      for share of o;
    if not found then
      raise exception using errcode = '22023', message = 'REPORT_OBJECT_MISSING';
    end if;
  else
    -- No messages, exception bodies, URLs, credentials or arbitrary nested JSON.
    if p_report_path is not null or p_failure_reason is null
       or jsonb_typeof(p_failure_reason) is distinct from 'object' then
      raise exception using errcode = '22023', message = 'FAILURE_REASON_INVALID';
    end if;
    if not (p_failure_reason ?& array['code', 'stage', 'retryable'])
       or (p_failure_reason - array['code', 'stage', 'retryable']) <> '{}'::jsonb
       or jsonb_typeof(p_failure_reason -> 'code') is distinct from 'string'
       or jsonb_typeof(p_failure_reason -> 'stage') is distinct from 'string'
       or (p_failure_reason -> 'retryable') is distinct from 'false'::jsonb
       or (p_failure_reason ->> 'code') not in ('INPUT_INVALID', 'INPUT_HASH_MISMATCH',
         'INPUT_SIZE_MISMATCH', 'INPUT_DOWNLOAD_FAILED', 'RECONCILIATION_FAILED',
         'CONFIG_INVALID', 'COMPETITOR_PROFILE_INVALID', 'PROVIDER_ENRICHMENT_FAILED',
         'REPORT_GENERATION_FAILED', 'REPORT_UPLOAD_FAILED', 'UNEXPECTED_TASK_ERROR')
       or (p_failure_reason ->> 'stage') not in ('task', 'worker', 'ingestion',
         'reconciliation', 'config', 'competitors', 'provider', 'report', 'storage') then
      raise exception using errcode = '22023', message = 'FAILURE_REASON_INVALID';
    end if;
    v_reason := jsonb_build_object('code', p_failure_reason ->> 'code',
      'stage', p_failure_reason ->> 'stage', 'retryable', false);
  end if;
  -- Re-read wall clock after object locks: lock waits must not extend a lease.
  v_now := clock_timestamp();
  update public.task_runs set status = p_status, report_path = p_report_path,
    rule_version = p_rule_version, config_version = p_config_version,
    provider_snapshot_version = p_provider_snapshot_version,
    failure_reason = v_reason, completed_at = v_now, lease_until = null
    where run_id = p_run_id and lease_token = p_lease_token
      and status = 'processing' and lease_until > v_now;
  if not found then return false; end if;
  update public.tasks set status = p_status, completed_at = v_now,
    current_stage = case when p_status = 'completed' then 'report' else v_reason ->> 'stage' end,
    failure_reason = v_reason where task_id = v_task.task_id;
  insert into public.audit_events(store_id, task_id, run_id, event_type, result, metadata)
    values (v_task.store_id, v_task.task_id, p_run_id, 'run_finished', p_status,
      coalesce(v_reason, '{}'::jsonb));
  return true;
end;
$$;

create or replace function public.kwcc_rerun_task(
  p_task_id uuid, p_previous_run_id uuid, p_run_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_task public.tasks%rowtype;
  v_previous public.task_runs%rowtype;
  v_existing public.task_runs%rowtype;
  v_strategy_id uuid;
begin
  if v_uid is null then
    raise exception using errcode = '42501', message = 'STORE_ACCESS_DENIED';
  end if;
  if p_task_id is null or p_previous_run_id is null or p_run_id is null
     or p_run_id = p_previous_run_id then
    raise exception using errcode = '22023', message = 'RERUN_INPUT_INVALID';
  end if;
  select * into v_task from public.tasks where task_id = p_task_id for update;
  if not found or not public.has_store_access(v_task.store_id) then
    raise exception using errcode = '42501', message = 'STORE_ACCESS_DENIED';
  end if;
  select * into v_previous from public.task_runs
    where run_id = p_previous_run_id and task_id = p_task_id for update;
  if not found or v_previous.status not in ('completed', 'failed') then
    raise exception using errcode = '22023', message = 'PREVIOUS_RUN_NOT_TERMINAL';
  end if;
  select * into v_existing from public.task_runs where run_id = p_run_id;
  if found then
    if v_existing.task_id is distinct from p_task_id
       or v_existing.previous_run_id is distinct from p_previous_run_id then
      raise exception using errcode = '23505', message = 'JOB_ID_CONFLICT';
    end if;
    return jsonb_build_object('task_id', p_task_id, 'run_id', p_run_id, 'status', 'pending');
  end if;
  if v_task.status not in ('completed', 'failed') or v_task.input_size is null
     or exists (select 1 from public.task_runs where task_id = p_task_id
       and status in ('pending', 'processing'))
     or exists (select 1 from public.task_runs where previous_run_id = p_previous_run_id) then
    raise exception using errcode = '22023', message = 'TASK_NOT_RERUNNABLE';
  end if;
  -- A new run uses the currently selected strategy, while prior run snapshots
  -- and reports remain immutable. Replaying this run ID never reselects it.
  select s.config_id into v_strategy_id from public.strategy_configs s
    where s.store_id = v_task.store_id and s.product_stage = v_task.product_stage
      and (s.asin = v_task.self_asin or s.asin is null)
    order by (s.asin = v_task.self_asin) desc nulls last,
      s.created_at desc, s.config_id desc limit 1;
  insert into public.task_runs(run_id, task_id, previous_run_id, strategy_id, status)
    values (p_run_id, p_task_id, p_previous_run_id, v_strategy_id, 'pending');
  update public.tasks set status = 'pending', current_stage = 'ingestion',
    failure_reason = null, completed_at = null where task_id = p_task_id;
  insert into public.audit_events(user_id, store_id, task_id, run_id, event_type, metadata)
    values (v_uid, v_task.store_id, p_task_id, p_run_id, 'task_rerun_submitted',
      jsonb_build_object('previous_run_id', p_previous_run_id));
  return jsonb_build_object('task_id', p_task_id, 'run_id', p_run_id, 'status', 'pending');
exception when unique_violation then
  raise exception using errcode = '23505', message = 'JOB_ID_CONFLICT';
end;
$$;

-- Explicitly close default PUBLIC EXECUTE and any ACL from a prior application.
revoke all on function public.kwcc_submit_task(uuid, uuid, uuid, text, text, text, text, bigint, uuid) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_submit_task(uuid, uuid, uuid, text, text, text, text, bigint, uuid) to authenticated;
revoke all on function public.kwcc_rerun_task(uuid, uuid, uuid) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_rerun_task(uuid, uuid, uuid) to authenticated;
revoke all on function public.kwcc_claim_run(text, int) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_claim_run(text, int) to service_role;
revoke all on function public.kwcc_heartbeat_run(uuid, uuid, int) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_heartbeat_run(uuid, uuid, int) to service_role;
revoke all on function public.kwcc_finish_run(uuid, uuid, text, text, text, text, text, jsonb) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_finish_run(uuid, uuid, text, text, text, text, text, jsonb) to service_role;

commit;
