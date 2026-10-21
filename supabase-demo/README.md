# Decision log on Supabase

I'm Raghav R, AVP at Karbon Card. My work is zero-to-one: taking a sales motion, a GTM channel or an ops process from nothing to something that runs. To do that without a big team, I built my own team of AI agents, and then the plumbing they needed. This is one piece of that plumbing.

My agents send their ranking, routing and go/skip questions to a decision router. Each answer comes back with a verdict and a confidence. Once a dozen agents were making hundreds of calls a week, I needed one place to see every call, catch the shaky ones and review the week. I built that on Supabase. This repo is the working version, running live on real (anonymised) data.

Live project: https://fshgpqmlryokrccmtuet.supabase.co

## What it shows
- **Every agent decision is logged with its confidence.** One row per answer in `public.decisions`: area, question type (`choice`, `score` or `yes_no`), verdict, score, confidence, model version and a `rubric_only` flag for calls that didn't use a model.
- **Low-confidence calls are flagged for a human by the database itself.** `needs_human` is a generated column, `confidence < 0.5`, so no agent can forget to set it.
- **A weekly summary view.** `public.weekly_summary` gives calls, low-confidence calls and average confidence per week and area. This is what my weekly review reads.
- **Locked down by default.** Row level security is on and the base table has no public grants at all. Writes need the service role key. The publishable key can read only the two anonymised views, `public.decisions_public` and `public.weekly_summary`. Neither exposes `run_ref`.

## The seed data is real, and anonymised
`supabase/seed.sql` holds **1,375 real decisions from 110 decision-router run files, 25 Sep to 19 Oct 2026 (IST)**. Only numbers and generic labels were kept: area, question type, verdict label, score, confidence, model, timestamp and an opaque run id (`run-001` ...). Every question, input, name, company and amount was stripped. Choice labels that named a person, a brand or an amount are `null`.

Things to know when reading it:
- Times are day-level for most runs (midnight IST) because the run files only carry a date. 19 rows from 3 files have no reliable date, so `created_at` is `null` and they are left out of the weekly view.
- For `yes_no` answers the router returns a probability, not a confidence. `score` holds P(yes), the verdict is `yes` when P ≥ 0.5, and `confidence` is `null`, so these rows are never auto-flagged.
- The seed counts every response file on disk, so the week of 5 Oct shows 558 calls. My weekly review that week counted 446 from its own dump, which left out several hiring shortlist files.

## How the access lockdown works
`0002_lock_anon_to_view.sql` closes `public.decisions` to the `anon` and `authenticated` roles completely. The public views read their rows through `private.decisions_public_rows()`, a security definer function that returns only the anonymised columns. It lives in a `private` schema the Data API doesn't expose, so it can't be called directly, and the views themselves stay `security_invoker`. I checked it with the publishable key:

| Request | Result |
|---|---|
| `GET /rest/v1/decisions` | 401, permission denied |
| `POST /rest/v1/decisions` | 401 |
| `GET /rest/v1/decisions_public` (count=exact) | 1,375 rows |
| `GET /rest/v1/weekly_summary` | 25 week × area rows |
| `POST /rest/v1/rpc/decisions_public_rows` | 404, not exposed |

The Supabase security advisor reports one info-level note: RLS is on for `public.decisions` with no policies. That's deliberate. No public role should read it.

## Query the live project
Use the project's publishable key (from the dashboard, never the service role key):
```bash
export SUPABASE_URL=https://fshgpqmlryokrccmtuet.supabase.co
export SUPABASE_KEY=<publishable key>

# Human review queue, lowest confidence first
curl "$SUPABASE_URL/rest/v1/decisions_public?needs_human=is.true&order=confidence.asc&limit=20" \
  -H "apikey: $SUPABASE_KEY" -H "Authorization: Bearer $SUPABASE_KEY"

# Total row count
curl -I "$SUPABASE_URL/rest/v1/decisions_public?select=id" -H "Prefer: count=exact" \
  -H "apikey: $SUPABASE_KEY" -H "Authorization: Bearer $SUPABASE_KEY"

# Weekly summary
curl "$SUPABASE_URL/rest/v1/weekly_summary?order=week.desc" \
  -H "apikey: $SUPABASE_KEY" -H "Authorization: Bearer $SUPABASE_KEY"
```

## Run it yourself
**Locally with the Supabase CLI**
```bash
cd supabase-demo
supabase init        # only if there's no supabase/config.toml yet
supabase start
supabase db reset    # applies migrations 0001 and 0002, then seed.sql
```
**In a hosted project:** open the SQL editor and paste `supabase/migrations/0001_decision_log.sql`, then `0002_lock_anon_to_view.sql`, then `supabase/seed.sql`.

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
- `supabase/migrations/0002_lock_anon_to_view.sql`: closes the base table, views read via a private function
- `supabase/seed.sql`: 1,375 anonymised real decisions
- `scripts/log_decision.ts`: inserts one router response as decision rows (supabase-js)
- `examples/jev_response.sample.json`: a made-up response to test the script
- `.env.example`: the env vars the script reads (no keys)

## What's next
Today outcomes aren't tracked against verdicts, so there is no accuracy number yet. I'm building an `outcomes` table keyed on `decisions.id` next, so every go/skip can be scored against what actually happened. That turns the log from a record of what my agents decided into a measure of how good their judgement is, which is what I need to decide which calls they can make without me.
