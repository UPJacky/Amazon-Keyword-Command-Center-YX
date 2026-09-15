-- LUNU-05 R12: bind Provider budget admission to the task/run that was previewed.
-- The function locks the previewed pair, delegates the existing lease logic,
-- and rolls back the nested claim if the queue head changed meanwhile.
begin;

create or replace function public.kwcc_claim_previewed_run(
  p_worker_id text, p_lease_seconds int,
  p_task_id uuid, p_run_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_expected record;
  v_claim jsonb;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;
  if p_task_id is null or p_run_id is null then
    raise exception using errcode = '22023', message = 'PREVIEW_INPUT_INVALID';
  end if;

  -- Wait for the previewed pair. If another Worker already took it, the
  -- status check fails and this call returns null without claiming anything.
  select t.task_id, r.run_id into v_expected
    from public.tasks t join public.task_runs r on r.task_id = t.task_id
   where t.task_id = p_task_id and r.run_id = p_run_id
     and t.status = 'pending' and r.status = 'pending'
   for update of t, r;
  if not found then
    return null;
  end if;

  -- kwcc_claim_run owns the existing lease/expired-run rules. The nested
  -- block is a subtransaction: a changed queue head is rolled back rather
  -- than leaving a different task in processing state.
  begin
    v_claim := public.kwcc_claim_run(p_worker_id, p_lease_seconds);
    if v_claim is null
       or v_claim -> 'task' ->> 'task_id' is distinct from p_task_id::text
       or v_claim -> 'run' ->> 'run_id' is distinct from p_run_id::text then
      raise exception using errcode = 'P0001', message = 'PREVIEW_STALE';
    end if;
    return v_claim;
  exception when sqlstate 'P0001' then
    return null;
  end;
end;
$$;

revoke all on function public.kwcc_claim_previewed_run(text, int, uuid, uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.kwcc_claim_previewed_run(text, int, uuid, uuid)
  to service_role;

commit;
