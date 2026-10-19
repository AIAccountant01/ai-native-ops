-- Decision log for an AI agent team.
-- Every ranking, routing and go/skip call an agent makes is stored with its confidence.
-- Calls under 0.5 confidence are flagged for a human by a generated column.

create extension if not exists pgcrypto;  -- gen_random_uuid() (built in on Postgres 13+, kept for older setups)

create table if not exists public.decisions (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz default now(),   -- null only for imported rows with no reliable date
  area          text,                       -- e.g. hiring, cos, routing_field, sales_icp, mentor
  question_type text not null
                check (question_type in ('choice', 'score', 'yes_no')),
  verdict       text,                       -- generic label for choice / yes_no; null for score
  score         numeric,                    -- score value; for yes_no rows, P(yes)
  confidence    numeric check (confidence between 0 and 1),
  needs_human   boolean generated always as (confidence < 0.5) stored,
  model         text,                       -- decision model version, e.g. jev-1.13.0
  rubric_only   boolean not null default false,  -- true when no model call was made
  run_ref       text                        -- pointer to the private run file (opaque id)
);

comment on table  public.decisions is 'One row per agent decision: verdict, score and confidence.';
comment on column public.decisions.needs_human is 'True when confidence < 0.5; these go to a human review queue.';

create index if not exists decisions_created_at_idx  on public.decisions (created_at desc);
create index if not exists decisions_area_created_idx on public.decisions (area, created_at desc);
create index if not exists decisions_needs_human_idx on public.decisions (created_at desc) where needs_human;
create index if not exists decisions_run_ref_idx     on public.decisions (run_ref);

-- Row level security: the table is closed by default.
-- Writes come from a trusted server process with the service role key (which bypasses RLS).
-- The anon role can only read, and only the anonymised columns (no run_ref).
alter table public.decisions enable row level security;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;           -- present on Supabase; created here for plain Postgres
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
end $$;

revoke all on public.decisions from anon, authenticated;
grant select (id, created_at, area, question_type, verdict, score, confidence,
              needs_human, model, rubric_only)
  on public.decisions to anon, authenticated;

drop policy if exists "anon read-only" on public.decisions;
create policy "anon read-only" on public.decisions
  for select to anon, authenticated
  using (true);

-- Anonymised public view: no run_ref. security_invoker makes the caller's RLS and grants apply.
create or replace view public.decisions_public
  with (security_invoker = true) as
select id, created_at, area, question_type, verdict, score, confidence,
       needs_human, model, rubric_only
from public.decisions;

-- Weekly roll-up (weeks start Monday, Asia/Kolkata).
create or replace view public.weekly_summary
  with (security_invoker = true) as
select
  date_trunc('week', created_at at time zone 'Asia/Kolkata')::date        as week,
  area,
  count(*)                                                                as calls,
  count(*) filter (where needs_human)                                     as low_confidence_calls,
  round(avg(confidence), 2)                                               as avg_confidence
from public.decisions
where created_at is not null
group by 1, 2;

-- Supabase gives new relations broad default grants; keep the views read-only.
revoke all on public.decisions_public, public.weekly_summary from anon, authenticated;
grant select on public.decisions_public, public.weekly_summary to anon, authenticated;
