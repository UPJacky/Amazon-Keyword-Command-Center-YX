-- LUNU-04 E05: persist business inputs and human confirmation metadata.
-- Additive migration: old tasks and the original submit RPC remain readable.

alter table public.tasks add column if not exists primary_core_keyword text;
alter table public.tasks add column if not exists competitor_selection_version text;
alter table public.tasks add column if not exists product_facts_version text;
alter table public.tasks add column if not exists feature_review_version text;
alter table public.tasks add column if not exists checklist_version text;

create table if not exists public.task_confirmations (
  confirmation_id uuid primary key default gen_random_uuid(),
  object_id text not null,
  version text not null,
  store_id uuid not null references public.stores(store_id),
  task_id uuid references public.tasks(task_id) on delete cascade,
  self_asin text not null,
  status text not null check (status in ('draft', 'confirmed', 'rejected')),
  items jsonb not null check (jsonb_typeof(items) = 'array'),
  confirmed_by uuid references auth.users(id),
  confirmed_at timestamptz,
  input_hash text not null,
  created_at timestamptz not null default now(),
  unique (object_id, version, store_id)
);

alter table public.task_confirmations enable row level security;
drop policy if exists task_confirmations_member_read on public.task_confirmations;
create policy task_confirmations_member_read on public.task_confirmations
  for select to authenticated using (public.has_store_access(store_id));
revoke all on table public.task_confirmations from public, anon, authenticated;
grant select on table public.task_confirmations to authenticated;

create or replace function public.kwcc_save_task_confirmation(
  p_object_id text, p_version text, p_store_id uuid, p_task_id uuid,
  p_self_asin text, p_status text, p_items jsonb, p_input_hash text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := auth.uid(); v_row public.task_confirmations%rowtype;
begin
  if v_uid is null or p_store_id is null or not public.has_store_access(p_store_id) then
    raise exception using errcode = '42501', message = 'STORE_ACCESS_DENIED';
  end if;
  if p_status not in ('draft', 'confirmed', 'rejected') or jsonb_typeof(p_items) is distinct from 'array'
     or p_input_hash !~ '^[0-9a-fA-F]{64}$' then
    raise exception using errcode = '22023', message = 'CONFIRMATION_INPUT_INVALID';
  end if;
  if p_status = 'confirmed' and p_task_id is null then
    raise exception using errcode = '22023', message = 'CONFIRMATION_TASK_REQUIRED';
  end if;
  insert into public.task_confirmations(object_id, version, store_id, task_id, self_asin, status,
    items, confirmed_by, confirmed_at, input_hash)
  values (p_object_id, p_version, p_store_id, p_task_id, p_self_asin, p_status, p_items,
    case when p_status = 'confirmed' then v_uid else null end,
    case when p_status = 'confirmed' then now() else null end, p_input_hash)
  on conflict (object_id, version, store_id) do update set
    task_id = excluded.task_id, self_asin = excluded.self_asin, status = excluded.status,
    items = excluded.items, confirmed_by = excluded.confirmed_by,
    confirmed_at = excluded.confirmed_at, input_hash = excluded.input_hash;
  select * into v_row from public.task_confirmations
    where object_id = p_object_id and version = p_version and store_id = p_store_id;
  return to_jsonb(v_row);
end;
$$;

revoke all on function public.kwcc_save_task_confirmation(text, text, uuid, uuid, text, text, jsonb, text)
  from public, anon, authenticated, service_role;
grant execute on function public.kwcc_save_task_confirmation(text, text, uuid, uuid, text, text, jsonb, text)
  to authenticated;
