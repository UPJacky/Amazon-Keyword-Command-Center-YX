-- LUNU-05 R12: read-only admission preview for the server worker.
-- This function never claims, updates, or requeues a task.  It returns only
-- the non-secret task projection needed for conservative Provider budgeting;
-- the worker still performs a cache-aware preflight after downloading input.
begin;

create or replace function public.kwcc_preview_next_run()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_task record;
begin
  if auth.role() is distinct from 'service_role' then
    raise exception using errcode = '42501', message = 'WORKER_ONLY';
  end if;

  select t.task_id, t.store_id, t.self_asin, t.competitor_asins,
         t.core_keywords, t.primary_core_keyword, r.run_id,
         s.marketplace
    into v_task
    from public.tasks t
    join public.task_runs r on r.task_id = t.task_id
    join public.stores s on s.store_id = t.store_id
   where t.status = 'pending' and r.status = 'pending'
   order by r.created_at, r.run_id
   limit 1;

  if not found then
    return null;
  end if;

  return jsonb_build_object(
    'task', jsonb_build_object(
      'task_id', v_task.task_id,
      'store_id', v_task.store_id,
      'self_asin', v_task.self_asin,
      'competitor_asins', v_task.competitor_asins,
      'core_keywords', v_task.core_keywords,
      'primary_core_keyword', v_task.primary_core_keyword,
      'marketplace', v_task.marketplace
    ),
    'run', jsonb_build_object('run_id', v_task.run_id, 'task_id', v_task.task_id)
  );
end;
$$;

revoke all on function public.kwcc_preview_next_run() from public, anon, authenticated, service_role;
grant execute on function public.kwcc_preview_next_run() to service_role;

commit;
