-- Private report objects are written by the Worker with service-role credentials.
-- Signed-in users may only read the exact object recorded for a run belonging
-- to one of their stores. No authenticated INSERT/UPDATE/DELETE policy exists.

insert into storage.buckets (id, name, public)
values ('reports', 'reports', false)
on conflict (id) do update
set public = false;

drop policy if exists reports_member_read on storage.objects;

create policy reports_member_read
on storage.objects for select
to authenticated
using (
  bucket_id = 'reports'
  and array_length(storage.foldername(name), 1) = 2
  and exists (
    select 1
    from public.task_runs tr
    join public.tasks t on t.task_id = tr.task_id
    where tr.task_id::text = (storage.foldername(name))[1]
      and tr.run_id::text = (storage.foldername(name))[2]
      and tr.report_path = name
      and public.has_store_access(t.store_id)
  )
);
