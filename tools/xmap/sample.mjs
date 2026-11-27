#!/usr/bin/env node
// xmap triage-sample: a reproducible sample of triage decisions for an independent audit.
//   node tools/xmap/sample.mjs <handle> [--n 15] [--seed 1]
// Draws up to n posts from each of four strata (skipped by rule, skipped on reading, kept by rule, kept on reading)
// and prints each with its decision, the post's own text and the text it quotes. The same seed always gives the
// same sample; a new audit round uses a new seed so it covers different posts.
import path from 'node:path';
import crypto from 'node:crypto';
import { accountDir, readJsonl, parseArgs } from './lib/util.mjs';

export function sample(handle, n = 15, seed = '1') {
  const dir = accountDir(handle);
  const byId = new Map(readJsonl(path.join(dir, 'posts.jsonl')).map(p => [p.id, p]));
  const rank = id => crypto.createHash('sha1').update(`${seed}:${id}`).digest('hex');
  const strata = { 'skip/rule': [], 'skip/judged': [], 'keep/rule': [], 'keep/judged': [] };
  for (const t of readJsonl(path.join(dir, 'triage.jsonl'))) {
    if (/^repost:/.test(t.reason || '')) continue;
    strata[`${t.keep ? 'keep' : 'skip'}/${/^auto:/.test(t.reason || '') ? 'rule' : 'judged'}`].push(t);
  }
  const out = [];
  for (const [name, rows] of Object.entries(strata)) {
    const pick = rows.map(t => [rank(t.id), t]).sort((a, b) => (a[0] < b[0] ? -1 : 1)).slice(0, n).map(x => x[1]);
    for (const t of pick) out.push({ stratum: name, of: rows.length, ...t, post: byId.get(t.id) });
  }
  return out;
}
const one = s => (s || '').replace(/\s+/g, ' ').trim();

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2));
  if (!a._[0]) { console.error('usage: sample.mjs <handle> [--n 15] [--seed 1]'); process.exit(2); }
  const rows = sample(a._[0].replace(/^@/, ''), Number(a.n || 15), String(a.seed || '1'));
  let cur = '';
  for (const r of rows) {
    if (r.stratum !== cur) { cur = r.stratum; console.log(`\n== ${cur} (${rows.filter(x => x.stratum === cur).length} of ${r.of})`); }
    const p = r.post || {};
    console.log(`[p:${r.id}] ${(p.created_at || '').slice(0, 10)} ${p.kind} | ${r.reason}`);
    console.log(`   own:    ${one(p.text) || '(no text)'}`);
    if (p.quoted) console.log(`   quotes: @${p.quoted.handle || '?'} ${(p.quoted.created_at || '').slice(0, 10)}: ${one(p.quoted.text) || '(no text)'}`);
  }
  console.log(`\nsampled=${rows.length} seed=${a.seed || '1'}`);
}
