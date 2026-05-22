-- Run this in Supabase SQL Editor.
create table if not exists public.chat_sessions (
  user_id text primary key,
  data jsonb not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Optional trigger to keep updated_at fresh.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists chat_sessions_touch_updated_at on public.chat_sessions;
create trigger chat_sessions_touch_updated_at
before update on public.chat_sessions
for each row execute function public.touch_updated_at();

-- If using service role key in backend, these policies are not strictly required.
-- Keep RLS explicit if you plan to use anon/authenticated keys later.
alter table public.chat_sessions enable row level security;

-- Example permissive policy for backend service role workflows.
drop policy if exists chat_sessions_all_service on public.chat_sessions;
create policy chat_sessions_all_service
on public.chat_sessions
as permissive
for all
to service_role
using (true)
with check (true);
