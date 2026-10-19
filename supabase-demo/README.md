# Decision log on Supabase

A small, working demo of how I'd run the decision layer of my agent team on Postgres.

My agents send their ranking, routing and go/skip questions to a decision router. Each answer comes back
with a verdict and a confidence. This demo stores every one of those answers in a Supabase table, so the
whole team's judgement can be queried, audited and reviewed in one place.

## What it shows

- **Every agent decision is logged with its confidence.** One row per answer in `public.decisions`:
  area, question type (`choice`, `score` or `yes_no`), verdict, score, confidence, model version and a
  `rubric_only` flag for calls that didn't use a model.
- **Low-confidence calls are flagged for a human by the database itself.** `needs_human` is a generated
  column, `confidence < 0.5`, so no agent can forget to set it.
- **A weekly summary view.** `public.weekly_summary` gives calls, low-confidence calls and average
  confidence per week and area. This is what my weekly review reads.
- **Locked down by default.** Row level security is on. Writes need the service role key. The `anon` role
  can only read the anonymised columns, through `public.decisions_public` and `public.weekly_summary`.

## The seed data is real, and anonymised

`supabase/seed.sql` holds **1,375 real decisions from 110 decision-router run files, 25 Sep to 19 Oct 2026
(IST)**. Only numbers and generic labels were kept: area, question type, verdict label, score,
confidence, model, timestamp and an opaque run id (`run-001` ...). Every question, input, name, company and
amount was stripped. Choice labels that named a person, a brand or an amount are `null`.

Things to know when reading it:
- Times are day-level for most runs (midnight IST) because the run files only carry a date. 19 rows from
  3 files have no reliable date, so `created_at` is `null` and they are left out of the weekly view.
- For `yes_no` answers the router returns a probability, not a confidence. `score` holds P(yes), the
  verdict is `yes` when P ≥ 0.5, and `confidence` is `null`, so these rows are never auto-flagged.
- The seed counts every response file on disk, so the week of 5 Oct shows 558 calls. My weekly review
  that week counted 446 from its own dump, which left out several hiring shortlist files.

## Run it

**Locally with the Supabase CLI**
```bash
cd supabase-demo
supabase init        # only if there's no supabase/config.toml yet
supabase start
supabase db reset    # applies migrations/0001_decision_log.sql, then seed.sql
```

**In a hosted project:** open the SQL editor and paste `supabase/migrations/0001_decision_log.sql`, then
`supabase/seed.sql`.

**Log new decisions from a router response**
```bash
npm install
cp .env.example .env   # fill in SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; never commit it
set -a; source .env; set +a
npx tsx scripts/log_decision.ts examples/jev_response.sample.json cos
# -> Logged 3 decisions, 1 flagged for a human (confidence < 0.5).
```

## Example queries

```sql
-- 1. This week's human review queue: everything under 0.5 confidence
select created_at, area, question_type, verdict, score, confidence
from public.decisions_public
where needs_human
  and created_at >= date_trunc('week', now())
order by confidence asc;

-- 2. Which areas need the most human attention?
select area,
       sum(calls)                                                as calls,
       sum(low_confidence_calls)                                 as low_conf,
       round(100.0 * sum(low_confidence_calls) / sum(calls), 1)  as low_conf_pct
from public.weekly_summary
group by area
order by low_conf_pct desc;

-- 3. Week-on-week trend for the whole team
select week, sum(calls) as calls, sum(low_confidence_calls) as low_conf,
       round(avg(avg_confidence), 2) as avg_conf_across_areas
from public.weekly_summary
group by week
order by week;
```

## Files

- `supabase/migrations/0001_decision_log.sql`: table, indexes, generated flag, RLS, views
- `supabase/seed.sql`: 1,375 anonymised real decisions
- `scripts/log_decision.ts`: inserts one router response as decision rows (supabase-js)
- `examples/jev_response.sample.json`: a made-up response to test the script
- `.env.example`: the env vars the script reads (no keys)

## What's next

Today outcomes aren't tracked against verdicts, so there is no accuracy number yet. The next step is an
`outcomes` table keyed on `decisions.id`, so every go/skip can be scored against what actually happened.
