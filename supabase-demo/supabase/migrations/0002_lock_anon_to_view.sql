drop policy if exists "anon read-only" on public.decisions;
revoke all on public.decisions from anon, authenticated;

create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to anon, authenticated;

create or replace function private.decisions_public_rows()
returns table (id uuid, created_at timestamptz, area text, question_type text, verdict text,
  score numeric, confidence numeric, needs_human boolean, model text, rubric_only boolean)
language sql stable security definer set search_path = ''
as $$ select d.id, d.created_at, d.area, d.question_type, d.verdict, d.score, d.confidence,
            d.needs_human, d.model, d.rubric_only from public.decisions d; $$;
revoke all on function private.decisions_public_rows() from public;
grant execute on function private.decisions_public_rows() to anon, authenticated;

create or replace view public.decisions_public with (security_invoker = true) as
select * from private.decisions_public_rows();

create or replace view public.weekly_summary with (security_invoker = true) as
select date_trunc('week', created_at at time zone 'Asia/Kolkata')::date as week, area,
       count(*) as calls, count(*) filter (where needs_human) as low_confidence_calls,
       round(avg(confidence), 2) as avg_confidence
from private.decisions_public_rows() where created_at is not null group by 1, 2;

revoke all on public.decisions_public, public.weekly_summary from anon, authenticated;
grant select on public.decisions_public, public.weekly_summary to anon, authenticated;
