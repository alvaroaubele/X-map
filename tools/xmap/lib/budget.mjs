// Read budget. X rate-limits the operator's session by how many posts it has been served, whichever account
// they belong to (run 1: `blocked:rate_limited` after about 6,800 reads in one day, docs/LESSONS.md A6). So the
// budget is one number for the whole repository over a rolling 24 hours, counted from the raw runs themselves.
import fs from 'node:fs';
import path from 'node:path';
import { ROOT, readJson } from './util.mjs';

export const DEFAULT_READ_BUDGET = 6000;
export const readBudget = () => Number((readJson(path.join(ROOT, 'xmap.json'), {}) || {}).read_budget_per_day ?? DEFAULT_READ_BUDGET);
const runTime = id => { const m = id.match(/^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)Z$/); return m ? Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`) : NaN; };

// Signed-in runs that started within the 24 hours before `now`, across every account, with the posts each read.
// A run that never wrote run.json (killed mid-capture) still counts: its rows are in articles.jsonl.
export function readsLast24h(now = Date.now()) {
  const out = []; const accounts = path.join(ROOT, 'accounts');
  if (!fs.existsSync(accounts)) return out;
  for (const h of fs.readdirSync(accounts)) {
    const raw = path.join(accounts, h, 'raw');
    if (!fs.existsSync(raw)) continue;
    for (const r of fs.readdirSync(raw)) {
      const t = runTime(r);
      if (!(t > now - 864e5 && t <= now)) continue;
      const man = readJson(path.join(raw, r, 'run.json'), null);
      if (man && man.auth !== 'session') continue;
      const open = path.join(raw, r, 'articles.jsonl');
      const reads = man ? Number(man.posts_captured || 0) : fs.existsSync(open) ? fs.readFileSync(open, 'utf8').split('\n').filter(Boolean).length : 0;
      out.push({ handle: h, run_id: r, reads, finished: !!man });
    }
  }
  return out.sort((a, b) => (a.run_id < b.run_id ? -1 : 1));
}
export function budgetState(now = Date.now()) {
  const runs = readsLast24h(now); const budget = readBudget();
  const used = runs.reduce((s, r) => s + r.reads, 0);
  return { budget, used, remaining: Math.max(0, budget - used), runs };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const s = budgetState();
  for (const r of s.runs) console.log(`  ${r.run_id} ${r.handle} reads=${r.reads}${r.finished ? '' : ' (unfinished run)'}`);
  console.log(`read_budget_per_day=${s.budget} used_last_24h=${s.used} remaining=${s.remaining}`);
}
