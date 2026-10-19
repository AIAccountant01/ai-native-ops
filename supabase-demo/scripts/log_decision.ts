// Log decision-router (Jev) answers to Supabase, one row per answer.
//
// Usage:
//   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
//     npx tsx scripts/log_decision.ts path/to/jev_response.json [area] [run_ref]
//
// Keys come from the environment only. Never commit them.
// Inserts need the service role key: under RLS the anon key is read-only by design.
// SUPABASE_ANON_KEY is accepted so you can point it at a project where you have added an insert policy.
//
// Accepts a Jev response shaped like
//   { "model": "jev-1.13.0", "answers": { "<id>": { "type": "score", "score": 6.2, "confidence": 0.71 }, ... } }
// or the same object under a "response" key. Only numbers and the verdict label are stored;
// question ids, instructions and inputs are dropped.

import { readFileSync } from "node:fs";
import { createClient } from "@supabase/supabase-js";

type JevAnswer =
  | { type: "score"; score: number; confidence?: number }
  | { type: "choice"; choice: string; confidence?: number }
  | { type: "noul"; noul: number };

type DecisionRow = {
  area: string | null;
  question_type: "choice" | "score" | "yes_no";
  verdict: string | null;
  score: number | null;
  confidence: number | null;
  model: string | null;
  rubric_only: boolean;
  run_ref: string | null;
};

function toRow(
  a: JevAnswer,
  model: string | null,
  rubricOnly: boolean,
  area: string | null,
  runRef: string | null,
): DecisionRow | null {
  const conf = (c?: number) => (typeof c === "number" && c >= 0 && c <= 1 ? c : null);
  const base = { area, model, rubric_only: rubricOnly, run_ref: runRef };
  switch (a.type) {
    case "score":
      return { ...base, question_type: "score", verdict: null, score: a.score, confidence: conf(a.confidence) };
    case "choice":
      return { ...base, question_type: "choice", verdict: a.choice, score: null, confidence: conf(a.confidence) };
    case "noul": // yes/no probability: store P(yes) as score; the API returns no separate confidence
      return { ...base, question_type: "yes_no", verdict: a.noul >= 0.5 ? "yes" : "no", score: a.noul, confidence: null };
    default:
      return null;
  }
}

async function main() {
  const [file, area = null, runRef = null] = process.argv.slice(2);
  if (!file) {
    console.error("usage: log_decision.ts <jev_response.json> [area] [run_ref]");
    process.exit(2);
  }
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.SUPABASE_ANON_KEY;
  if (!url || !key) {
    console.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY).");
    process.exit(2);
  }

  const raw = JSON.parse(readFileSync(file, "utf8"));
  const resp = raw.response ?? raw;
  const model: string | null = typeof resp.model === "string" ? resp.model : null;
  const answers: Record<string, JevAnswer> = resp.answers ?? {};
  // Set "rubric_only": true in the file when the verdict came from a written rubric, not a model call.
  const rubricOnly = raw.rubric_only === true || resp.rubric_only === true;

  const rows = Object.values(answers)
    .map((a) => toRow(a, model, rubricOnly, area, runRef))
    .filter((r): r is DecisionRow => r !== null);
  if (rows.length === 0) {
    console.error("No answers found in", file);
    process.exit(1);
  }

  const supabase = createClient(url, key, { auth: { persistSession: false } });
  const { data, error } = await supabase.from("decisions").insert(rows).select("id, needs_human");
  if (error) {
    console.error("Insert failed:", error.message);
    process.exit(1);
  }
  const flagged = data.filter((r) => r.needs_human).length;
  console.log(`Logged ${data.length} decisions, ${flagged} flagged for a human (confidence < 0.5).`);
}

main();
