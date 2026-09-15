-- LUNU-05 R02/R03/R06: expose the immutable, task-bound buyer confirmation
-- to the worker claim.  This is additive to 007-009: old tasks with no
-- confirmation remain valid and produce draft business evidence.

create or replace function public.kwcc_save_task_confirmation(
  p_object_id text, p_version text, p_store_id uuid, p_task_id uuid,
  p_self_asin text, p_status text, p_items jsonb, p_input_hash text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_task public.tasks%rowtype;
  v_existing public.task_confirmations%rowtype;
begin
  if v_uid is null or p_store_id is null or not public.has_store_access(p_store_id) then
    raise exception using errcode = '42501', message = 'STORE_ACCESS_DENIED';
  end if;
  if p_object_id is null or p_object_id not in ('buyer-checklist', 'feature-review')
     or p_version is null or p_version !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
     or p_self_asin is null or p_self_asin !~ '^B0[A-Z0-9]{8}$'
     or p_status not in ('draft', 'confirmed', 'rejected')
     or jsonb_typeof(p_items) is distinct from 'array'
     or p_input_hash is null or p_input_hash !~ '^[0-9a-fA-F]{64}$' then
    raise exception using errcode = '22023', message = 'CONFIRMATION_INPUT_INVALID';
  end if;
  if p_status = 'confirmed' and p_task_id is null then
    raise exception using errcode = '22023', message = 'CONFIRMATION_TASK_REQUIRED';
  end if;
  if p_task_id is not null then
    select * into v_task from public.tasks where task_id = p_task_id;
    if not found or v_task.store_id is distinct from p_store_id
       or v_task.self_asin is distinct from p_self_asin then
      raise exception using errcode = '22023', message = 'CONFIRMATION_TASK_STORE_ASIN_MISMATCH';
    end if;
  end if;

  select * into v_existing from public.task_confirmations
    where object_id = p_object_id and version = p_version and store_id = p_store_id
    for update;
  if found and v_existing.status = 'confirmed' then
    if v_existing.task_id is distinct from p_task_id
       or v_existing.self_asin is distinct from p_self_asin
       or v_existing.status is distinct from p_status
       or v_existing.items is distinct from p_items
       or lower(v_existing.input_hash) is distinct from lower(p_input_hash) then
      raise exception using errcode = '23505', message = 'CONFIRMATION_VERSION_IMMUTABLE';
    end if;
    return to_jsonb(v_existing);
  end if;
  if found and (v_existing.task_id is distinct from p_task_id
                or v_existing.self_asin is distinct from p_self_asin) then
    raise exception using errcode = '23505', message = 'CONFIRMATION_VERSION_IDENTITY_IMMUTABLE';
  end if;

  insert into public.task_confirmations(object_id, version, store_id, task_id, self_asin, status,
    items, confirmed_by, confirmed_at, input_hash)
  values (p_object_id, p_version, p_store_id, p_task_id, p_self_asin, p_status, p_items,
    case when p_status = 'confirmed' then v_uid else null end,
    case when p_status = 'confirmed' then now() else null end, lower(p_input_hash))
  on conflict (object_id, version, store_id) do update set
    task_id = excluded.task_id, self_asin = excluded.self_asin, status = excluded.status,
    items = excluded.items, confirmed_by = excluded.confirmed_by,
    confirmed_at = excluded.confirmed_at, input_hash = excluded.input_hash;
  select * into v_existing from public.task_confirmations
    where object_id = p_object_id and version = p_version and store_id = p_store_id;
  return to_jsonb(v_existing);
end;
$$;

revoke all on function public.kwcc_save_task_confirmation(text, text, uuid, uuid, text, text, jsonb, text)
  from public, anon, authenticated, service_role;
grant execute on function public.kwcc_save_task_confirmation(text, text, uuid, uuid, text, text, jsonb, text)
  to authenticated;

create or replace function public.kwcc_claim_run(
  p_worker_id text, p_lease_seconds int default 300
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_expired record;
  v_task public.tasks%rowtype;
  v_run public.task_runs%rowtype;
  v_config jsonb;
  v_now timestamptz;
  v_confirmation jsonb;
  v_reason jsonb := '{"code":"LEASE_EXPIRED","stage":"worker","retryable":false}'::jsonb;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;
  if p_worker_id is null or p_worker_id !~ '^[A-Za-z0-9_.:-]{1,128}$'
     or p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 3600 then
    raise exception using errcode = '22023', message = 'LEASE_INPUT_INVALID';
  end if;
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
  select to_jsonb(c) into v_confirmation
    from public.task_confirmations c
    where c.object_id = 'buyer-checklist'
      and c.version = v_task.confirmation_version
      and c.store_id = v_task.store_id
      and c.task_id = v_task.task_id
      and c.self_asin = v_task.self_asin
      and c.status = 'confirmed'
    order by c.confirmed_at desc nulls last, c.confirmation_id desc
    limit 1;
  insert into public.audit_events(store_id, task_id, run_id, event_type)
    values (v_task.store_id, v_task.task_id, v_run.run_id, 'run_claimed');
  return jsonb_build_object('task', to_jsonb(v_task) || jsonb_build_object(
    'marketplace', (select s.marketplace from public.stores s where s.store_id = v_task.store_id)),
    'business_confirmation', v_confirmation, 'run', to_jsonb(v_run), 'config', v_config);
end;
$$;

revoke all on function public.kwcc_claim_run(text, int) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_claim_run(text, int) to service_role;
