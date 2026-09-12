-- LUNU-04 hardening: a confirmation belongs to one task identity and a
-- confirmed version is immutable.  Keep 007 as historical migration; this
-- replacement is additive and safe to apply after 008.

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
  if p_object_id is null or p_object_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
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

  -- A supplied task id is never just a caller-provided label.  It must be the
  -- same store and ASIN, otherwise a member of one store could attach an
  -- otherwise valid confirmation to another task's history.
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
  if found then
    if v_existing.task_id is distinct from p_task_id
       or v_existing.self_asin is distinct from p_self_asin then
      raise exception using errcode = '23505', message = 'CONFIRMATION_VERSION_IDENTITY_IMMUTABLE';
    end if;
    -- Confirmed evidence is an auditable version, not a mutable draft.  An
    -- exact replay remains idempotent; every identity/content change is
    -- rejected instead of rewriting historical evidence.
    if v_existing.status = 'confirmed' then
      if v_existing.task_id is distinct from p_task_id
         or v_existing.self_asin is distinct from p_self_asin
         or v_existing.status is distinct from p_status
         or v_existing.items is distinct from p_items
         or lower(v_existing.input_hash) is distinct from lower(p_input_hash) then
        raise exception using errcode = '23505', message = 'CONFIRMATION_VERSION_IMMUTABLE';
      end if;
      return to_jsonb(v_existing);
    end if;
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
