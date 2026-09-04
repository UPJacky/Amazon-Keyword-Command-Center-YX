-- Local migration only; requires 001-003. No heads table or historical rewrites.
begin;

-- config-0.1 is the exact shape of rules/defaults/*.json, not config-1.0.
-- Limits below are validation ceilings, not business defaults. Integer counts
-- are bounded at 1e9; monetary spend at 1e12; ratios at [0,1].
create or replace function public.kwcc_validate_strategy(
  p_product_stage text, p_config jsonb, p_config_version text, p_rule_version text
) returns void language plpgsql set search_path = '' as $$
declare
  v_shape constant jsonb := '{
    "evidence":{"insufficient_clicks_max":[0,1000000000,true],"preliminary_clicks_min":[0,1000000000,true],"sufficient_clicks_min":[0,1000000000,true],"preliminary_orders_min":[0,1000000000,true],"sufficient_orders_min":[0,1000000000,true]},
    "acos":{"target":[0,1,false],"tolerance":[0,1,false],"break_even":[0,1,false]},
    "stop_loss":{"zero_order_clicks":[0,1000000000,true],"zero_order_spend":[0,1000000000000,false]},
    "market":{"high_search_volume":[0,1,false],"high_opportunity_min":[0,1,false]},
    "organic_defense":{"core_max_rank":[1,1000000000,true],"max_defense_acos":[0,1,false]},
    "diagnostics":{"low_ctr":[0,1,false],"low_cvr":[0,1,false]}
  }'::jsonb;
  v_section text;
  v_fields jsonb;
  v_name text;
  v_bounds jsonb;
  v_number numeric;
begin
  if p_product_stage is null or p_product_stage not in
    ('new', 'growth', 'stable', 'clearance', 'seasonal_restart')
    or p_config_version is null or p_config_version !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$'
    -- Both shipped rule definitions are explicit: legacy report generator
    -- worker/report/generate_report.py and rules/action_mapping.json.
    or p_rule_version is null or p_rule_version not in ('rule-v0.1', 'rules-1.0') then
    raise exception using errcode = '22023', message = 'STRATEGY_VERSION_INVALID';
  end if;
  if jsonb_typeof(p_config) is distinct from 'object' then
    raise exception using errcode = '22023', message = 'STRATEGY_CONFIG_INVALID';
  end if;
  if p_config->'schema_version' is distinct from to_jsonb('config-0.1'::text)
    or p_config->'config_version' is distinct from to_jsonb(p_config_version)
    or p_config->'product_stage' is distinct from to_jsonb(p_product_stage)
    or (p_config - array['schema_version','config_version','product_stage',
      'evidence','acos','stop_loss','market','organic_defense','diagnostics']) <> '{}'::jsonb then
    raise exception using errcode = '22023', message = 'STRATEGY_SHAPE_INVALID';
  end if;
  for v_section, v_fields in select key, value from jsonb_each(v_shape) loop
    if jsonb_typeof(p_config->v_section) is distinct from 'object' then
      raise exception using errcode = '22023', message = 'STRATEGY_SECTION_INVALID';
    end if;
    if exists (select 1 from jsonb_object_keys(p_config->v_section) as keys(key)
      where not (v_fields ? key)) then
      raise exception using errcode = '22023', message = 'STRATEGY_UNKNOWN_FIELD';
    end if;
    for v_name, v_bounds in select key, value from jsonb_each(v_fields) loop
      -- JSON strings, nulls and bools fail before any numeric cast. JSONB itself
      -- rejects bare NaN/Infinity; strings spelling them also fail this guard.
      if jsonb_typeof(p_config->v_section->v_name) is distinct from 'number' then
        raise exception using errcode = '22023', message = 'STRATEGY_NUMBER_REQUIRED';
      end if;
      v_number := (p_config->v_section->>v_name)::numeric;
      if v_number::text in ('NaN', 'Infinity', '-Infinity')
        or v_number < (v_bounds->>0)::numeric or v_number > (v_bounds->>1)::numeric
        or ((v_bounds->>2)::boolean and v_number <> trunc(v_number)) then
        raise exception using errcode = '22023', message = 'STRATEGY_NUMBER_OUT_OF_RANGE';
      end if;
    end loop;
  end loop;
  if (p_config#>>'{acos,target}')::numeric > (p_config#>>'{acos,tolerance}')::numeric
    or (p_config#>>'{acos,tolerance}')::numeric > (p_config#>>'{acos,break_even}')::numeric
    or (p_config#>>'{evidence,insufficient_clicks_max}')::numeric >= (p_config#>>'{evidence,preliminary_clicks_min}')::numeric
    or (p_config#>>'{evidence,preliminary_clicks_min}')::numeric > (p_config#>>'{evidence,sufficient_clicks_min}')::numeric
    or (p_config#>>'{evidence,preliminary_orders_min}')::numeric > (p_config#>>'{evidence,sufficient_orders_min}')::numeric then
    raise exception using errcode = '22023', message = 'STRATEGY_BOUNDARY_ORDER_INVALID';
  end if;
end;
$$;

-- Private common implementation; only the two public RPCs can call it.
create or replace function public.kwcc_append_strategy(
  p_store_id uuid, p_asin text, p_product_stage text, p_config jsonb,
  p_config_version text, p_rule_version text, p_config_id uuid, p_source_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_row public.strategy_configs%rowtype;
  v_created_at timestamptz;
begin
  -- Never trust a global profile role or membership of another store.
  if v_uid is null or p_store_id is null or not exists (
    select 1 from public.store_memberships sm
    where sm.store_id = p_store_id and sm.user_id = v_uid and sm.role = 'admin'
  ) then
    raise exception using errcode = '42501', message = 'STRATEGY_ADMIN_REQUIRED';
  end if;
  if p_config_id is null then
    raise exception using errcode = '22023', message = 'STRATEGY_ID_REQUIRED';
  end if;
  perform public.kwcc_validate_strategy(p_product_stage, p_config, p_config_version, p_rule_version);
  -- Serialize request IDs before checking existence; no ON CONFLICT UPDATE.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('strategy-id:' || p_config_id::text, 0));
  select * into v_row from public.strategy_configs where config_id = p_config_id;
  if found then
    if v_row.store_id is distinct from p_store_id or v_row.asin is distinct from p_asin
      or v_row.product_stage is distinct from p_product_stage
      or v_row.config_version is distinct from p_config_version
      or v_row.rule_version is distinct from p_rule_version or v_row.config is distinct from p_config
      or (p_source_id is not null and not exists (
        select 1 from public.audit_events ae where ae.store_id = p_store_id
        and ae.event_type = 'strategy_rollback'
        and ae.metadata->>'config_id' = p_config_id::text
        and ae.metadata->>'source_config_id' = p_source_id::text
      )) then
      raise exception using errcode = '23505', message = 'STRATEGY_ID_CONFLICT';
    end if;
    return to_jsonb(v_row);
  end if;
  -- Latest created_at wins. Serialize scope publication and force strictly
  -- increasing timestamps even within one transaction or clock adjustment.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('strategy-scope:' || p_store_id::text || ':' || p_product_stage, 0));
  if exists (select 1 from public.strategy_configs where store_id = p_store_id
    and product_stage = p_product_stage and asin is not distinct from p_asin
    and config_version = p_config_version) then
    raise exception using errcode = '23505', message = 'STRATEGY_VERSION_CONFLICT';
  end if;
  select greatest(clock_timestamp(), coalesce(max(created_at) + interval '1 microsecond', clock_timestamp()))
    into v_created_at from public.strategy_configs
    where store_id = p_store_id and product_stage = p_product_stage;
  insert into public.strategy_configs(config_id, store_id, asin, product_stage,
    config_version, rule_version, config, created_by, created_at)
    values (p_config_id, p_store_id, p_asin, p_product_stage, p_config_version,
      p_rule_version, p_config, v_uid, v_created_at) returning * into v_row;
  insert into public.audit_events(user_id, store_id, event_type, metadata)
    values (v_uid, p_store_id, case when p_source_id is null then 'strategy_save' else 'strategy_rollback' end,
      jsonb_build_object('config_id', p_config_id, 'source_config_id', p_source_id,
        'config_version', p_config_version, 'rule_version', p_rule_version, 'product_stage', p_product_stage));
  return to_jsonb(v_row);
end;
$$;

create or replace function public.kwcc_save_strategy(
  p_store_id uuid, p_product_stage text, p_config jsonb, p_config_version text,
  p_rule_version text, p_config_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  -- Internal append performs the store-scoped membership authorization.
  return public.kwcc_append_strategy(p_store_id, null, p_product_stage, p_config,
    p_config_version, p_rule_version, p_config_id, null);
end;
$$;

create or replace function public.kwcc_rollback_strategy(
  p_config_id uuid, p_new_config_id uuid, p_config_version text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_source public.strategy_configs%rowtype;
  v_uid uuid := auth.uid();
begin
  select * into v_source from public.strategy_configs where config_id = p_config_id;
  if not found or v_uid is null or v_source.store_id is null or not exists (
    select 1 from public.store_memberships sm where sm.store_id = v_source.store_id
      and sm.user_id = v_uid and sm.role = 'admin'
  ) then
    raise exception using errcode = '42501', message = 'STRATEGY_ADMIN_REQUIRED';
  end if;
  if p_new_config_id is null or p_new_config_id = p_config_id
    or p_config_version is null or p_config_version = v_source.config_version then
    raise exception using errcode = '22023', message = 'STRATEGY_NEW_VERSION_REQUIRED';
  end if;
  perform public.kwcc_validate_strategy(v_source.product_stage, v_source.config,
    v_source.config_version, v_source.rule_version);
  return public.kwcc_append_strategy(v_source.store_id, v_source.asin, v_source.product_stage,
    jsonb_set(v_source.config, '{config_version}', to_jsonb(p_config_version), false),
    p_config_version, v_source.rule_version, p_new_config_id, p_config_id);
end;
$$;

revoke all on function public.kwcc_validate_strategy(text, jsonb, text, text) from public, anon, authenticated;
revoke all on function public.kwcc_append_strategy(uuid, text, text, jsonb, text, text, uuid, uuid) from public, anon, authenticated;
revoke all on function public.kwcc_save_strategy(uuid, text, jsonb, text, text, uuid) from public, anon, authenticated;
revoke all on function public.kwcc_rollback_strategy(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.kwcc_save_strategy(uuid, text, jsonb, text, text, uuid) to authenticated;
grant execute on function public.kwcc_rollback_strategy(uuid, uuid, text) to authenticated;

-- RLS read policies remain unchanged; no direct historical writes from clients.
revoke insert, update, delete on public.strategy_configs from public, anon, authenticated;
commit;
