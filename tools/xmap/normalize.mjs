#!/usr/bin/env node
// xmap normalize: fold every raw run of an account into the canonical, diff-friendly dataset.
//   accounts/<handle>/posts.jsonl   one post per line, newest first, keyed by post id (idempotent upsert)
//   accounts/<handle>/profile.json  latest profile snapshot
// Raw runs are never modified; re-running this is always safe and reproduces the same files.
// Rows extracted by an older extractor are re-read from their stored raw_html with the current one (lib/reparse),
// and gaps the DOM cannot fill are taken from the run's own captured API responses (lib/net).
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJson, writeJson, readJsonl, writeJsonl, snowflakeDate, parseMetrics, cmpIdDesc, parseArgs, TOOL_VERSION } from './lib/util.mjs';
import { isStale, reparse } from './lib/reparse.mjs';
import { loadNet, enrich, loadProfile } from './lib/net.mjs';

export function kindOf(raw, handle) {
  const own = raw.handle.toLowerCase() === handle.toLowerCase();
  if (!own) return 'repost';
  if (raw.replying_to && raw.replying_to.length) return 'reply';
  if (raw.quoted) return 'quote';
  return 'post';
}
const uniq = a => [...new Set(a)];
export function entities(text) {
  const t = text || '';
  return {
    mentions: uniq([...t.matchAll(/(?<![A-Za-z0-9_])@([A-Za-z0-9_]{1,15})/g)].map(m => m[1].toLowerCase())),
    hashtags: uniq([...t.matchAll(/(?<![A-Za-z0-9_&])#([\p{L}\p{N}_]+)/gu)].map(m => m[1].toLowerCase())),
    cashtags: uniq([...t.matchAll(/(?<![A-Za-z0-9_])\$([A-Za-z]{1,6}(?:\.[A-Za-z]{1,2})?)(?![A-Za-z0-9_])/g)].map(m => m[1].toUpperCase())),
  };
}
// The quoted post as the page showed it. id is null when neither the card nor the API records gave one;
// `unavailable` marks a quoted post X withheld (deleted, protected, limited), with X's notice as `notice`.
const quotedOf = q => {
  if (!q) return null;
  if (q.unavailable) return { id: q.id || null, handle: q.handle || null, unavailable: true, notice: q.text || '', url: q.id && q.handle ? `https://x.com/${q.handle}/status/${q.id}` : null };
  if (!q.id && !q.handle) return { ref: q.ref || null };
  const d = q.id ? snowflakeDate(q.id) : null;
  return {
    id: q.id || null, handle: q.handle, name: q.name || '', text: q.text || '',
    url: q.id ? `https://x.com/${q.handle}/status/${q.id}` : null,
    created_at: d ? d.toISOString() : (q.created_at || null),
    links: uniq((q.links || []).map(l => l.url)), media: (q.media || []).length, replying_to: q.replying_to || [],
    quoted: q.quoted && q.quoted.handle ? { id: q.quoted.id || null, handle: q.quoted.handle, text: q.quoted.text || '' } : null,
  };
};

export function toPost(raw, handle) {
  const d = snowflakeDate(raw.id);
  return {
    id: raw.id, url: `https://x.com/${raw.handle}/status/${raw.id}`,
    author: raw.handle, author_name: raw.name, kind: kindOf(raw, handle),
    created_at: d ? d.toISOString() : null, date_display: raw.date_display,
    pinned: /pinned/i.test(raw.context || ''), context: raw.context || '',
    lang: raw.lang, text: raw.text, truncated: !!raw.truncated,
    ...entities(raw.text),
    links: uniq((raw.links || []).map(l => l.url)),
    media: (raw.media || []).map(m => ({ type: m.type, url: m.url || m.poster || '', alt: m.alt || '' })),
    replying_to: raw.replying_to || [], in_reply_to_id: raw.in_reply_to_id || null,
    quoted: quotedOf(raw.quoted),
    metrics: parseMetrics(raw.metrics_label), metrics_at: raw.captured_at,
    first_seen: raw.captured_at, last_seen: raw.captured_at,
    surfaces: [raw.surface], runs: [raw.run_id],
  };
}

export async function normalize(handle) {
  const dir = accountDir(handle);
  const rawRoot = path.join(dir, 'raw');
  const runs = fs.existsSync(rawRoot) ? fs.readdirSync(rawRoot).filter(r => fs.existsSync(path.join(rawRoot, r, 'run.json'))).sort() : [];
  const rowsByRun = runs.map(r => readJsonl(path.join(rawRoot, r, 'articles.jsonl.gz')));
  const stale = rowsByRun.flat().filter(isStale);
  const fresh = new Map((await reparse(stale)).map(r => [`${r.run_id}|${r.seq}`, r]));
  const net = loadNet(runs.map(r => path.join(rawRoot, r)));
  const byId = new Map(); let profile = null;
  for (const [i, r] of runs.entries()) {
    const man = readJson(path.join(rawRoot, r, 'run.json'));
    // The page's own user record is exact; the DOM header read is the fallback (and was wrong signed-in in 1.0.0).
    const api = loadProfile(path.join(rawRoot, r), handle);
    if (api || man.profile) profile = { ...(api || { ...man.profile, source: 'dom' }), captured_at: (man.profile && man.profile.captured_at) || man.ended_at || null, run_id: r };
    for (const row of rowsByRun[i]) {
      const raw = enrich(fresh.get(`${row.run_id}|${row.seq}`) || row, net);
      const p = toPost(raw, handle); const prev = byId.get(p.id);
      if (!prev) { byId.set(p.id, p); continue; }
      // Later observations win for mutable fields; a full text never gets replaced by a truncated one.
      const keepText = !prev.truncated && p.truncated;
      byId.set(p.id, {
        ...prev, ...p,
        ...(keepText ? { text: prev.text, truncated: false, mentions: prev.mentions, hashtags: prev.hashtags, cashtags: prev.cashtags, links: prev.links } : {}),
        pinned: prev.pinned || p.pinned, context: p.context || prev.context,
        first_seen: prev.first_seen, surfaces: uniq([...prev.surfaces, ...p.surfaces]).sort(), runs: uniq([...prev.runs, ...p.runs]).sort(),
      });
    }
  }
  const posts = [...byId.values()].sort((a, b) => cmpIdDesc(a.id, b.id));
  writeJsonl(path.join(dir, 'posts.jsonl'), posts);
  if (profile) writeJson(path.join(dir, 'profile.json'), profile);
  return { handle, runs: runs.length, posts: posts.length, profile: !!profile, reparsed: stale.length, net_records: net.size, tool_version: TOOL_VERSION };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2));
  if (!a._[0]) { console.error('usage: normalize.mjs <handle>'); process.exit(2); }
  const r = await normalize(a._[0].replace(/^@/, ''));
  console.log(`normalized handle=${r.handle} runs=${r.runs} posts=${r.posts} profile=${r.profile} reparsed=${r.reparsed} net_records=${r.net_records}`);
}
