-- Run this once in the Supabase SQL Editor (Project → SQL Editor → New query).
-- Not applied automatically — this file is kept in the repo for reference/history only.
--
-- Effect: every INSERT into public.subscribers fires a GitHub repository_dispatch
-- event, which triggers .github/workflows/send-confirmation.yml to send the
-- confirmation email immediately instead of waiting for the next cron batch.

-- 1) Enable required extensions (skip if already enabled under Database → Extensions).
create extension if not exists pg_net with schema extensions;
create extension if not exists supabase_vault;

-- 2) Store the GitHub PAT (fine-grained, scoped to this repo only,
--    "Contents: Read and write" permission) — replace the placeholder below.
--    Idempotent: safe to re-run (e.g. when rotating the PAT later) — creates
--    the secret on first run, updates it in place on subsequent runs.
do $$
declare
  pat text := 'ghp_REPLACE_ME';
  existing_id uuid;
begin
  select id into existing_id from vault.decrypted_secrets where name = 'github_pat';
  if existing_id is null then
    perform vault.create_secret(pat, 'github_pat');
  else
    perform vault.update_secret(existing_id, new_secret => pat);
  end if;
end $$;

-- 3) Trigger function: fires the GitHub Actions dispatch event.
create or replace function public.trigger_send_confirmation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  perform net.http_post(
    url := 'https://api.github.com/repos/ultrahikerpp/invest-digest/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (
        select decrypted_secret from vault.decrypted_secrets where name = 'github_pat'
      ),
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object('event_type', 'send_confirmation')
  );
  return new;
end;
$$;

-- 4) Attach the trigger.
drop trigger if exists on_subscriber_insert_send_confirmation on public.subscribers;
create trigger on_subscriber_insert_send_confirmation
  after insert on public.subscribers
  for each row
  execute function public.trigger_send_confirmation();
