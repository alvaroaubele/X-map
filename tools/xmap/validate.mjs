#!/usr/bin/env node
// xmap validate: the acceptance gate. Prints one line per check and a final `pending=<n>`; exit 0 only at pending=0.
//   node tools/xmap/validate.mjs <handle> [--require-map] [--allow-logged-out]
// Data checks prove the dataset is internally consistent; map checks prove every citation and quotation in
// map.md resolves to a captured post, and that the map was written against the current dataset.
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJson, readJsonl, snowflakeDate, cmpIdDesc, parseArgs } from './lib/util.mjs';
import { timelineOwnIds } from './lib/net.mjs';

export const MAP_SECTIONS = ['Identity', 'Coverage', 'Themes', 'Theses and claims', 'Positions and predictions', 'Network', 'Sources and links', 'Signal posts', 'Open questions'];
const norm = s => s.normalize('NFKC').replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, ' ').trim().toLowerCase();

export function validate(handle, opts = {}) {
  const dir = accountDir(handle); const res = [];
  const check = (name, ok, detail = '') => res.push({ name, ok: !!ok, detail });
  const posts = readJsonl(path.join(dir, 'posts.jsonl'));
  const stats = readJson(path.join(dir, 'stats.json'), null);
  const profile = readJson(path.join(dir, 'profile.json'), null);
  const byId = new Map(posts.map(p => [p.id, p]));

  check('data.posts_present', posts.length > 0, `posts=${posts.length}`);
  check('data.ids_unique', byId.size === posts.length);
  check('data.sorted_newest_first', posts.every((p, i) => !i || cmpIdDesc(posts[i - 1].id, p.id) < 0));
  const bad = posts.filter(p => !/^\d+$/.test(p.id) || !p.author || !p.url || typeof p.text !== 'string' || !['post', 'reply', 'quote', 'repost'].includes(p.kind));
  check('data.schema', !bad.length, bad.length ? `bad ids: ${bad.slice(0, 5).map(p => p.id).join(',')}` : '');
  check('data.created_at_matches_id', posts.every(p => { const d = snowflakeDate(p.id); return d ? d.toISOString() === p.created_at : p.created_at === null; }));
  const empty = posts.filter(p => !p.text && !p.media.length && !p.quoted && !p.links.length);
  check('data.no_empty_posts', !empty.length, empty.length ? `empty: ${empty.slice(0, 5).map(p => p.id).join(',')}` : '');
  check('data.profile', profile && profile.handle && profile.handle.toLowerCase() === handle.toLowerCase(), profile ? `followers=${profile.followers}` : 'profile.json missing');
  check('data.stats_current', stats && stats.posts_total === posts.length, stats ? `stats.posts_total=${stats.posts_total}` : 'stats.json missing: run xmap stats');
  const lastRun = stats && stats.runs[stats.runs.length - 1];
  // The latest run passes when it ended ok, or when it was stopped (blocked, error) only after X had already served
  // the account's own timeline past the configured window start: then nothing inside the window is missing.
  let covered = '';
  if (lastRun && lastRun.status !== 'ok') {
    const acct = readJson(path.join(dir, 'account.json'), {}) || {};
    const cap = acct.capture || {};
    const sinceStr = cap.since || (cap.since_days != null ? new Date(Date.parse(lastRun.run_id.replace(/^(\d{4})(\d\d)(\d\d)T.*/, '$1-$2-$3')) - cap.since_days * 864e5).toISOString().slice(0, 10) : null);
    if (sinceStr) {
      const since = new Date(sinceStr + 'T00:00:00Z');
      const older = timelineOwnIds(path.join(dir, 'raw', lastRun.run_id), handle).map(snowflakeDate).filter(d => d && d < since);
      if (older.length) covered = ` window_covered: timeline served ${older.length} own posts before since=${sinceStr}`;
    }
  }
  check('run.latest_ok', lastRun && (lastRun.status === 'ok' || covered), lastRun ? `run=${lastRun.run_id} status=${lastRun.status} ${lastRun.stops.join(' ')}${covered}` : 'no run');
  check('run.signed_in', (lastRun && lastRun.auth === 'session') || opts.allowLoggedOut, lastRun ? `auth=${lastRun.auth}` : '');
  const trunc = posts.filter(p => p.truncated).length;
  check('data.full_text', trunc === 0, `truncated=${trunc}`);

  // Relevance triage (when the account uses it): one decision per post, in posts.jsonl order, none left unjudged.
  const triageFile = path.join(dir, 'triage.jsonl');
  const triage = fs.existsSync(triageFile) ? readJsonl(triageFile) : null;
  if (triage) {
    const same = triage.length === posts.length && triage.every((t, i) => t.id === posts[i].id);
    const unjudged = triage.filter(t => /^review:/.test(t.reason || '')).length;
    check('triage.current', same && !unjudged, `triage=${triage.length} posts=${posts.length} kept=${triage.filter(t => t.keep).length} unjudged=${unjudged}${same ? '' : ' (stale: run xmap triage)'}`);
  }
  const kept = triage ? new Set(triage.filter(t => t.keep).map(t => t.id)) : null;

  const mapFile = path.join(dir, 'map.md');
  if (fs.existsSync(mapFile) || opts.requireMap) {
    const md = fs.existsSync(mapFile) ? fs.readFileSync(mapFile, 'utf8') : '';
    check('map.present', !!md);
    const stamp = md.match(/<!--\s*xmap:\s*posts=(\d+)\s+run=(\S+)\s*-->/);
    check('map.dataset_stamp_current', stamp && stats && Number(stamp[1]) === stats.posts_total && stamp[2] === stats.latest_run,
      stamp ? `map posts=${stamp[1]} run=${stamp[2]}; dataset posts=${stats && stats.posts_total} run=${stats && stats.latest_run}` : 'missing <!-- xmap: posts=N run=RUN_ID -->');
    const heads = [...md.matchAll(/^## (.+)$/gm)].map(m => m[1].trim());
    const missing = MAP_SECTIONS.filter(s => !heads.includes(s));
    check('map.sections', !missing.length, missing.length ? `missing: ${missing.join('; ')}` : '');
    const cites = [...md.matchAll(/\[p:(\d+)\]/g)].map(m => m[1]);
    const dangling = [...new Set(cites.filter(id => !byId.has(id)))];
    check('map.citations_resolve', cites.length > 0 && !dangling.length, `citations=${cites.length} unresolved=${dangling.slice(0, 8).join(',') || 0}`);
    if (kept) {
      const skipped = [...new Set(cites.filter(id => byId.has(id) && !kept.has(id)))];
      check('map.citations_kept', !skipped.length, `skipped posts cited: ${skipped.slice(0, 8).join(',') || 0}`);
    }
    // Every analytic section must rest on cited posts.
    const parts = md.split(/^## /m).slice(1).map(s => ({ head: s.split('\n')[0].trim(), body: s }));
    const uncited = parts.filter(s => ['Themes', 'Theses and claims', 'Positions and predictions', 'Signal posts'].includes(s.head) && !/\[p:\d+\]/.test(s.body) && !/^_?none (found|captured)/im.test(s.body)).map(s => s.head);
    check('map.sections_cited', !uncited.length, uncited.length ? `no citations in: ${uncited.join('; ')}` : '');
    // Quotations: a blockquote line `> "text" [p:ID]` must be verbatim from that post (or the post it quotes).
    const misq = [];
    for (const m of md.matchAll(/^>\s*["\u201c](.+?)["\u201d]\s*\[p:(\d+)\]/gm)) {
      const p = byId.get(m[2]); if (!p) continue;
      const hay = norm(p.text + ' ' + ((p.quoted && p.quoted.text) || ''));
      if (!m[1].split(/\s*(?:\[\u2026\]|\[\.\.\.\])\s*/).every(seg => hay.includes(norm(seg)))) misq.push(m[2]);
    }
    check('map.quotes_verbatim', !misq.length, misq.length ? `not verbatim: ${misq.slice(0, 8).join(',')}` : '');
  }
  return res;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2), { 'require-map': 'bool', 'allow-logged-out': 'bool' });
  if (!a._[0]) { console.error('usage: validate.mjs <handle> [--require-map] [--allow-logged-out]'); process.exit(2); }
  const res = validate(a._[0].replace(/^@/, ''), { requireMap: a['require-map'], allowLoggedOut: a['allow-logged-out'] });
  for (const r of res) console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  ' + r.detail : ''}`);
  const pending = res.filter(r => !r.ok).length;
  console.log(`pending=${pending}`);
  process.exit(pending ? 1 : 0);
}
