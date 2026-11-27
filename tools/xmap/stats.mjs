#!/usr/bin/env node
// xmap stats: deterministic aggregates over posts.jsonl -> stats.json. Every number a map cites comes from here,
// so the interpretive layer never counts by hand. Output depends only on the dataset (no wall-clock fields).
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJson, writeJson, readJsonl, parseArgs } from './lib/util.mjs';

const top = (m, n = 25) => [...m.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, n).map(([k, v]) => ({ key: k, n: v }));
const inc = (m, k) => m.set(k, (m.get(k) || 0) + 1);
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const i = s.length >> 1; return s.length % 2 ? s[i] : Math.round((s[i - 1] + s[i]) / 2); };
const host = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return null; } };

export function stats(handle) {
  const dir = accountDir(handle);
  const posts = readJsonl(path.join(dir, 'posts.jsonl'));
  const h = handle.toLowerCase();
  const own = posts.filter(p => p.author.toLowerCase() === h);
  const dated = own.filter(p => p.created_at && !p.pinned).map(p => p.created_at).sort();
  const kinds = new Map(), months = new Map(), hours = new Map(), mentions = new Map(), reposted = new Map(), quotedA = new Map(),
    domains = new Map(), cash = new Map(), hash = new Map(), replyTo = new Map();
  for (const p of posts) {
    inc(kinds, p.kind);
    if (p.kind === 'repost') { inc(reposted, p.author.toLowerCase()); continue; }
    if (p.created_at) { inc(months, p.created_at.slice(0, 7)); inc(hours, p.created_at.slice(11, 13)); }
    p.mentions.forEach(m => inc(mentions, m)); p.cashtags.forEach(c => inc(cash, c)); p.hashtags.forEach(c => inc(hash, c));
    p.replying_to.forEach(r => inc(replyTo, r.toLowerCase()));
    if (p.quoted && p.quoted.handle) inc(quotedA, p.quoted.handle.toLowerCase());
    for (const u of [...p.links, ...((p.quoted && p.quoted.links) || [])]) { const d = host(u); if (d && !/^(x|twitter|t)\.com?$/.test(d) && d !== 't.co') inc(domains, d); }
  }
  const rank = k => own.filter(p => p.metrics[k] != null).sort((a, b) => b.metrics[k] - a.metrics[k] || (a.id < b.id ? 1 : -1)).slice(0, 20).map(p => ({ id: p.id, [k]: p.metrics[k], kind: p.kind, created_at: p.created_at }));
  const runsDir = path.join(dir, 'raw');
  const runs = fs.existsSync(runsDir) ? fs.readdirSync(runsDir).sort().map(r => readJson(path.join(runsDir, r, 'run.json'), null)).filter(Boolean) : [];
  const last = runs[runs.length - 1] || null;
  const out = {
    handle, posts_total: posts.length, own_total: own.length,
    window: { oldest: dated[0] || null, newest: dated[dated.length - 1] || null },
    runs: runs.map(r => ({ run_id: r.run_id, status: r.status, auth: r.auth, posts_captured: r.posts_captured, since: r.since, stops: r.surfaces.map(s => `${s.surface}:${s.stop_reason}`) })),
    latest_run: last ? last.run_id : null, latest_auth: last ? last.auth : null,
    by_kind: Object.fromEntries([...kinds.entries()].sort()),
    by_month: Object.fromEntries([...months.entries()].sort()),
    by_hour_utc: Object.fromEntries([...hours.entries()].sort()),
    truncated: posts.filter(p => p.truncated).length,
    engagement_median_own: { likes: median(own.map(p => p.metrics.likes).filter(v => v != null)), views: median(own.map(p => p.metrics.views).filter(v => v != null)), reposts: median(own.map(p => p.metrics.reposts).filter(v => v != null)) },
    top_mentions: top(mentions), top_reply_targets: top(replyTo), top_reposted_authors: top(reposted), top_quoted_authors: top(quotedA),
    top_domains: top(domains), cashtags: top(cash, 50), hashtags: top(hash, 50),
    top_by_likes: rank('likes'), top_by_views: rank('views'),
  };
  writeJson(path.join(dir, 'stats.json'), out);
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2));
  if (!a._[0]) { console.error('usage: stats.mjs <handle>'); process.exit(2); }
  const s = stats(a._[0].replace(/^@/, ''));
  console.log(`stats handle=${s.handle} posts=${s.posts_total} own=${s.own_total} window=${(s.window.oldest || '-').slice(0, 10)}..${(s.window.newest || '-').slice(0, 10)} auth=${s.latest_auth}`);
}
