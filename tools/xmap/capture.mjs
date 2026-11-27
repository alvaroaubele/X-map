#!/usr/bin/env node
// xmap capture: drive one stock, headed Chromium through one account's profile surfaces at reading pace
// and append what the page renders to an immutable raw run directory.
//
//   node tools/xmap/capture.mjs <handle> [--surfaces posts,replies,reposts,media] [--since YYYY-MM-DD] [--max N] [--max-minutes M] [--allow-logged-out]
//
// Auth: the signed-in session comes from the X_AUTH_TOKEN environment variable (the value of the x.com
// `auth_token` cookie; X_CT0 optional). It is placed in the browser's cookie jar only: never logged,
// never written to disk, never committed.
// Exit codes: 0 captured, 2 usage or review gate not confirmed, 3 auth failed, 4 blocked by X (challenge / rate
// limit / login wall), 5 the day's read budget is already spent.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { createRequire } from 'node:module';
import { ROOT, TOOL_VERSION, accountDir, readJson, writeJson, snowflakeDate, parseArgs, HANDLE_RE, netOperationKept } from './lib/util.mjs';
import { budgetState } from './lib/budget.mjs';

const require = createRequire(import.meta.url);
const args = parseArgs(process.argv.slice(2), { 'allow-logged-out': 'bool' });
const handle = (args._[0] || '').replace(/^@/, '');
if (!HANDLE_RE.test(handle)) { console.error('usage: capture.mjs <handle> [--surfaces posts,replies] [--since YYYY-MM-DD] [--max N]'); process.exit(2); }

const dir = accountDir(handle);
const cfg = readJson(path.join(dir, 'account.json'), {});
const cap = cfg.capture || {};
const surfaces = (args.surfaces || (cap.surfaces || ['posts']).join(',')).split(',').filter(Boolean);
const sinceStr = args.since || cap.since || new Date(Date.now() - (cap.since_days ?? 90) * 864e5).toISOString().slice(0, 10);
const since = new Date(sinceStr + 'T00:00:00Z');
const maxPosts = Number(args.max || cap.max_posts || 1500);
const maxMinutes = Number(args['max-minutes'] || cap.max_minutes || 45);
const SURFACE_URL = { posts: h => `https://x.com/${h}`, replies: h => `https://x.com/${h}/with_replies`, reposts: h => `https://x.com/${h}/reposts`, media: h => `https://x.com/${h}/media` };
// A repost carries the date of the original post, not of the repost, so the reposts tab cannot be cut at `since`:
// it is read newest-first up to a fixed number of posts instead.
const SURFACE_CAP = { reposts: Number(cap.max_reposts ?? 300) };
for (const s of surfaces) if (!SURFACE_URL[s]) { console.error(`unknown surface: ${s}`); process.exit(2); }

const token = process.env.X_AUTH_TOKEN || '';
if (!token && !args['allow-logged-out']) {
  console.error('auth_failed: X_AUTH_TOKEN is not set. See docs/SETUP.md, or pass --allow-logged-out for the few posts X shows without a session.');
  process.exit(3);
}
// Signed-in reads are spent against the operator's session, so two things are settled before the browser opens:
// the operator has answered the review gate for this account, and the day's read budget has room.
let readsLeft = Infinity;
if (token) {
  if (!(cfg.gate && cfg.gate.confirmed)) {
    console.error(`gate_missing: accounts/${handle.toLowerCase()}/account.json has no gate.confirmed. The operator answers the review gate (window, surfaces, relevance rule, amplification) before the first signed-in capture: see prompts/lead.md.`);
    process.exit(2);
  }
  const b = budgetState();
  readsLeft = b.remaining;
  if (readsLeft <= 0) {
    console.error(`read_budget: ${b.used} posts read in the last 24 hours, budget ${b.budget} (xmap.json). No capture until earlier runs age out: bin/xmap budget.`);
    process.exit(5);
  }
}

const runId = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
const runDir = path.join(dir, 'raw', runId);
fs.mkdirSync(runDir, { recursive: true });
const rawFile = path.join(runDir, 'articles.jsonl');
const extractSrc = fs.readFileSync(path.join(ROOT, 'tools/xmap/extract.js'), 'utf8');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const jitter = (lo, hi) => lo + Math.random() * (hi - lo);
const log = (...a) => console.log(`[xmap ${new Date().toISOString().slice(11, 19)}]`, ...a);

const { chromium } = require('playwright');
// Stock Chromium, headed, default fingerprint. No stealth patches, no user-agent override: if X challenges
// or refuses this browser the run stops and reports (see CLAUDE.md, "Capture conduct").
const browser = await chromium.launch({ channel: 'chromium', headless: false });
const context = await browser.newContext({ viewport: { width: 1280, height: 1400 }, locale: 'en-US' });
if (token) {
  const base = { domain: '.x.com', path: '/', secure: true, sameSite: 'None' };
  const cookies = [{ name: 'auth_token', value: token, httpOnly: true, ...base }];
  if (process.env.X_CT0) cookies.push({ name: 'ct0', value: process.env.X_CT0, httpOnly: false, ...base });
  await context.addCookies(cookies);
}
const page = await context.newPage();

// Passive record of JSON the page itself requested from X's API hosts (nothing is requested on our own).
// A timeline page carries about 20 posts, so the cap scales with max_posts: a fixed cap would silently drop the
// quoted ids, t.co targets and reply links of the oldest posts in a deep capture.
let netN = 0;
const NET_MAX = Math.max(400, Math.ceil(maxPosts / 10));
// The last timeline page X answered with an error instead of entries. A timeline that stops growing right after
// such a page did not end: X failed to serve the next page (seen 2026-11-27: DependencyError on UserOriginalsTimeline).
let timelineError = null;
const TIMELINE_OP = /^User(Originals)?Tweets(AndReplies)?$|^UserOriginalsTimeline$|^UserMedia$/;
page.on('response', async r => {
  try {
    const u = new URL(r.url());
    if (!/(^|\.)x\.com$/.test(u.hostname) || !/graphql/.test(u.pathname) || netN >= NET_MAX) return;
    const op = u.pathname.split('/').pop();
    if (!netOperationKept(op)) return; // operator-session responses (home feed, sidebars, Grok JWT) are never stored
    const body = await r.body();
    if (TIMELINE_OP.test(op)) {
      try {
        const j = JSON.parse(body.toString('utf8'));
        timelineError = j.errors && j.errors.length ? { op, name: j.errors[0].name || '', message: j.errors[0].message || '', at: new Date().toISOString() } : null;
      } catch { /* not JSON */ }
    }
    if (body.length < 300) return;
    fs.mkdirSync(path.join(runDir, 'net'), { recursive: true });
    fs.writeFileSync(path.join(runDir, 'net', `${String(netN++).padStart(4, '0')}-${op.replace(/\W/g, '')}.json.gz`), zlib.gzipSync(body));
  } catch { /* response body unavailable (navigation, cache): not an error */ }
});

const manifest = {
  run_id: runId, handle, tool_version: TOOL_VERSION, started_at: new Date().toISOString(), ended_at: null,
  auth: 'none', browser: `chromium ${browser.version()} headed`, since: sinceStr, max_posts: maxPosts,
  read_budget_left_at_start: Number.isFinite(readsLeft) ? readsLeft : null,
  surfaces: [], posts_captured: 0, profile: null, status: 'running', stop_detail: '',
};
const finish = async (status, detail, code) => {
  manifest.status = status; manifest.stop_detail = detail || ''; manifest.ended_at = new Date().toISOString();
  manifest.net_responses = netN;
  if (fs.existsSync(rawFile)) { fs.writeFileSync(rawFile + '.gz', zlib.gzipSync(fs.readFileSync(rawFile))); fs.unlinkSync(rawFile); }
  writeJson(path.join(runDir, 'run.json'), manifest);
  await browser.close();
  log(`status=${status} posts_captured=${manifest.posts_captured} run=${path.relative(ROOT, runDir)} ${detail || ''}`);
  process.exit(code);
};
const blockedBy = s => (s.login_flow ? 'login_flow' : s.challenge ? 'challenge' : s.rate_limited ? 'rate_limited' : '');
const snap = () => page.evaluate(extractSrc);

try {
  if (token) {
    await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(jitter(4000, 6000));
    const s = await snap();
    const authed = new URL(page.url()).pathname === '/home' && !s.signals.login_flow && !s.signals.signin_wall;
    if (!authed) await finish('auth_failed', `session not accepted (landed on ${new URL(page.url()).pathname}); the auth_token is expired, revoked or challenged`, 3);
    manifest.auth = 'session';
    log(`signed-in session confirmed; read budget left today: ${readsLeft}`);
  } else log('running WITHOUT a session: X shows only a handful of posts');

  const seen = new Set();
  const deadline = Date.now() + maxMinutes * 60000;
  let seq = 0;
  let budgetSpent = false;
  for (const surface of surfaces) {
    if (budgetSpent) break;
    const url = SURFACE_URL[surface](handle);
    const rec = { surface, url, steps: 0, new_posts: 0, stop_reason: '' };
    manifest.surfaces.push(rec);
    log(`surface=${surface} ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('article', { timeout: 30000 }).catch(() => {});
    await sleep(jitter(2500, 4500));
    let stale = 0, retries = 0; const recentOwn = [];
    for (;;) {
      const s = await snap();
      rec.steps++;
      const b = blockedBy(s.signals);
      if (b) { rec.stop_reason = `blocked:${b}`; await finish('blocked', `${b} on ${surface}`, 4); }
      if (s.profile && s.profile.handle.toLowerCase() === handle.toLowerCase()) manifest.profile = { ...s.profile, captured_at: new Date().toISOString() };
      let fresh = 0;
      for (const p of s.posts) {
        const key = `${p.id}|${p.context}`;
        if (seen.has(key)) continue;
        seen.add(key); fresh++;
        fs.appendFileSync(rawFile, JSON.stringify({ run_id: runId, surface, seq: seq++, captured_at: new Date().toISOString(), page_url: s.url, extractor_version: s.extractor_version, ...p }) + '\n');
        const pinned = /pinned/i.test(p.context);
        if (p.handle.toLowerCase() === handle.toLowerCase() && !pinned) { const d = snowflakeDate(p.id); if (d) recentOwn.push(d); }
      }
      rec.new_posts += fresh; manifest.posts_captured = seen.size;
      stale = fresh ? 0 : stale + 1;
      const tail = recentOwn.slice(-5);
      if (tail.length === 5 && tail.every(d => d < since)) { rec.stop_reason = 'reached_since'; break; }
      if (SURFACE_CAP[surface] && rec.new_posts >= SURFACE_CAP[surface]) { rec.stop_reason = 'surface_cap'; break; }
      if (seen.size >= readsLeft) { rec.stop_reason = 'read_budget'; budgetSpent = true; break; }
      if (seen.size >= maxPosts) { rec.stop_reason = 'max_posts'; break; }
      if (Date.now() > deadline) { rec.stop_reason = 'max_minutes'; break; }
      // X answered the next timeline page with a server error: do what a reader does. Wait, press the page's own
      // Retry / Try again control if it shows one, otherwise scroll back up and down so the page asks for the same
      // cursor again. At most three times per surface; after that the stop is reported as server_error.
      if (stale >= 3 && timelineError && retries < 3) {
        retries++; rec.retries = retries;
        const ctl = page.getByText(/^(Retry|Try again)$/);
        const hasCtl = await ctl.count().catch(() => 0);
        if (!rec.error_state) rec.error_state = await page.evaluate(() => {
          const c = document.querySelector('[data-testid="primaryColumn"]') || document.body;
          return c.innerText.slice(-600);
        }).catch(() => '');
        log(`  ${surface}: timeline error (${timelineError.name}); waiting, then ${hasCtl ? 'Retry control' : 'scroll back'} ${retries}/3`);
        await sleep(jitter(20000, 40000));
        timelineError = null;
        if (hasCtl) await ctl.first().click({ timeout: 10000 }).catch(() => {});
        else { await page.mouse.wheel(0, -2600); await sleep(jitter(3000, 5000)); await page.mouse.wheel(0, 3200); }
        await sleep(jitter(4000, 7000));
        stale = 0;
        continue;
      }
      if (stale >= 6) {
        rec.stop_reason = s.signals.signin_wall ? 'signin_wall' : timelineError ? 'server_error' : s.signals.error ? 'page_error' : 'end_of_timeline';
        if (timelineError) rec.stop_detail = `${timelineError.op}: ${timelineError.name} ${timelineError.message}`.trim();
        break;
      }
      if (rec.steps % 10 === 0) log(`  ${surface}: steps=${rec.steps} posts=${seen.size} oldest_own=${recentOwn.length ? recentOwn[recentOwn.length - 1].toISOString().slice(0, 10) : '-'}`);
      // Reading pace: one partial-viewport scroll, then a pause; a longer rest every 25 steps.
      await page.mouse.wheel(0, Math.round(jitter(900, 1300)));
      await sleep(jitter(1800, 4200));
      if (rec.steps % 25 === 0) await sleep(jitter(8000, 15000));
    }
    log(`  ${surface}: stop=${rec.stop_reason} steps=${rec.steps} new_posts=${rec.new_posts}`);
    await sleep(jitter(3000, 6000));
  }

  // Long posts render clipped behind "Show more" in timelines: read each one's own page for the full text.
  const clipped = fs.existsSync(rawFile)
    ? fs.readFileSync(rawFile, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)).filter(p => p.truncated)
    : [];
  const todo = budgetSpent ? [] : [...new Map(clipped.map(p => [p.id, p])).values()].slice(0, Number(cap.max_permalinks ?? 60));
  if (todo.length) {
    const rec = { surface: 'permalink', url: '', steps: 0, new_posts: 0, stop_reason: 'done' };
    manifest.surfaces.push(rec);
    log(`resolving ${todo.length} clipped posts on their own pages`);
    for (const t of todo) {
      if (Date.now() > deadline) { rec.stop_reason = 'max_minutes'; break; }
      await page.goto(`https://x.com/${t.handle}/status/${t.id}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForSelector('article', { timeout: 30000 }).catch(() => {});
      await sleep(jitter(2500, 5000));
      const s = await snap(); rec.steps++;
      const b = blockedBy(s.signals);
      if (b) { rec.stop_reason = `blocked:${b}`; await finish('blocked', `${b} on permalink`, 4); }
      const full = s.posts.find(p => p.id === t.id);
      if (full) {
        rec.new_posts++;
        fs.appendFileSync(rawFile, JSON.stringify({ run_id: runId, surface: 'permalink', seq: seq++, captured_at: new Date().toISOString(), page_url: s.url, extractor_version: s.extractor_version, ...full, context: t.context, replying_to: full.replying_to.length ? full.replying_to : t.replying_to }) + '\n');
      }
    }
  }
  await finish('ok', '', 0);
} catch (e) {
  await finish('error', String(e && e.message || e).split('\n')[0], 1);
}
