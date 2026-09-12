-- LUNU-05 R02: submit the business inputs together with the immutable file/run.
-- Additive wrapper: the original kwcc_submit_task remains available for old
-- clients and this function adds the typed business-input binding.
begin;

alter table public.tasks add column if not exists confirmation_version text;

create or replace function public.kwcc_submit_task_with_business_inputs(
  p_task_id uuid, p_run_id uuid, p_store_id uuid, p_self_asin text,
  p_product_stage text, p_input_file_path text, p_input_file_hash text,
  p_input_size bigint, p_strategy_id uuid default null,
  p_business_inputs jsonb default '{}'::jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_result jsonb;
  v_competitors jsonb := coalesce(p_business_inputs -> 'competitor_asins', '[]'::jsonb);
  v_keywords jsonb := coalesce(p_business_inputs -> 'core_keywords', '[]'::jsonb);
  v_primary text := nullif(btrim(p_business_inputs ->> 'primary_core_keyword'), '');
  v_item text;
begin
  if v_uid is null or jsonb_typeof(p_business_inputs) is distinct from 'object' then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;
  if v_primary is not null and (length(v_primary) > 200 or v_primary ~ '[\x00-\x1F\x7F-\x9F]') then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;
  if jsonb_typeof(v_competitors) is distinct from 'array'
     or jsonb_array_length(v_competitors) > 5
     or jsonb_typeof(v_keywords) is distinct from 'array'
     or jsonb_array_length(v_keywords) > 200 then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;
  for v_item in select value from jsonb_array_elements_text(v_competitors)
  loop
    if v_item !~ '^B0[A-Z0-9]{8}$' or v_item = p_self_asin then
      raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
    end if;
  end loop;
  if exists (select 1 from jsonb_array_elements_text(v_competitors) a
             group by value having count(*) > 1) then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;
  if exists (select 1 from jsonb_array_elements(v_keywords) a
             where jsonb_typeof(a) is distinct from 'string'
                or length(a #>> '{}') > 200
                or a #>> '{}' ~ '[\x00-\x1F\x7F-\x9F]') then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;
  if exists (select 1 from jsonb_each_text(p_business_inputs) kv
             where kv.key in ('competitor_selection_version', 'product_facts_version',
                              'feature_review_version', 'checklist_version', 'confirmation_version')
               and length(kv.value) > 128) then
    raise exception using errcode = '22023', message = 'BUSINESS_INPUTS_INVALID';
  end if;

  v_result := public.kwcc_submit_task(
    p_task_id, p_run_id, p_store_id, p_self_asin, p_product_stage,
    p_input_file_path, p_input_file_hash, p_input_size, p_strategy_id
  );
  update public.tasks
     set primary_core_keyword = v_primary,
         competitor_asins = v_competitors,
         core_keywords = v_keywords,
         competitor_selection_version = nullif(p_business_inputs ->> 'competitor_selection_version', ''),
         product_facts_version = nullif(p_business_inputs ->> 'product_facts_version', ''),
         feature_review_version = nullif(p_business_inputs ->> 'feature_review_version', ''),
         checklist_version = nullif(p_business_inputs ->> 'checklist_version', ''),
         confirmation_version = nullif(p_business_inputs ->> 'confirmation_version', '')
   where task_id = p_task_id and created_by = v_uid and store_id = p_store_id;
  if not found then
    raise exception using errcode = '42501', message = 'TASK_BINDING_FAILED';
  end if;
  return v_result;
end;
$$;

revoke all on function public.kwcc_submit_task_with_business_inputs(
  uuid, uuid, uuid, text, text, text, text, bigint, uuid, jsonb
) from public, anon, authenticated, service_role;
grant execute on function public.kwcc_submit_task_with_business_inputs(
  uuid, uuid, uuid, text, text, text, text, bigint, uuid, jsonb
) to authenticated;

commit;
