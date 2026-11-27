#!/usr/bin/env node
// xmap normalize: fold every raw run of an account into the canonical, diff-friendly dataset.
//   accounts/<handle>/posts.jsonl   one post per line, newest first, keyed by post id (idempotent upsert)
//   accounts/<handle>/profile.json  latest profile snapshot
// Raw runs are never modified; re-running this is always safe and reproduces the same files.
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJson, writeJson, readJsonl, writeJsonl, snowflakeDate, parseMetrics, cmpIdDesc, parseArgs, TOOL_VERSION } from './lib/util.mjs';

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
const quotedOf = q => !q ? null : q.id
  ? { id: q.id, handle: q.handle, name: q.name, text: q.text, url: `https://x.com/${q.handle}/status/${q.id}`, links: (q.links || []).map(l => l.url), media: (q.media || []).length }
  : { ref: q.ref || null };

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
    replying_to: raw.replying_to || [],
    quoted: quotedOf(raw.quoted),
    metrics: parseMetrics(raw.metrics_label), metrics_at: raw.captured_at,
    first_seen: raw.captured_at, last_seen: raw.captured_at,
    surfaces: [raw.surface], runs: [raw.run_id],
  };
}

export function normalize(handle) {
  const dir = accountDir(handle);
  const rawRoot = path.join(dir, 'raw');
  const runs = fs.existsSync(rawRoot) ? fs.readdirSync(rawRoot).filter(r => fs.existsSync(path.join(rawRoot, r, 'run.json'))).sort() : [];
  const byId = new Map(); let profile = null;
  for (const r of runs) {
    const man = readJson(path.join(rawRoot, r, 'run.json'));
    if (man.profile) profile = { ...man.profile, run_id: r };
    for (const raw of readJsonl(path.join(rawRoot, r, 'articles.jsonl.gz'))) {
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
  return { handle, runs: runs.length, posts: posts.length, profile: !!profile, tool_version: TOOL_VERSION };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2));
  if (!a._[0]) { console.error('usage: normalize.mjs <handle>'); process.exit(2); }
  const r = normalize(a._[0].replace(/^@/, ''));
  console.log(`normalized handle=${r.handle} runs=${r.runs} posts=${r.posts} profile=${r.profile}`);
}
