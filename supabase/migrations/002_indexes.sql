-- Performance indexes for the 001 baseline schema.
create index if not exists idx_store_memberships_user on public.store_memberships(user_id);
create index if not exists idx_tasks_store_created on public.tasks(store_id, created_at desc);
create index if not exists idx_tasks_status_created on public.tasks(status, created_at);
create index if not exists idx_task_runs_task_created on public.task_runs(task_id, created_at desc);
create index if not exists idx_audit_events_store_created on public.audit_events(store_id, created_at desc);

