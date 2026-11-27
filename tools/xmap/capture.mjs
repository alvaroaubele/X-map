#!/usr/bin/env node
// xmap capture: drive one stock, headed Chromium through one account's profile surfaces at reading pace
// and append what the page renders to an immutable raw run directory.
//
//   node tools/xmap/capture.mjs <handle> [--surfaces posts,replies] [--since YYYY-MM-DD] [--max N] [--max-minutes M] [--allow-logged-out]
//
// Auth: the signed-in session comes from the X_AUTH_TOKEN environment variable (the value of the x.com
// `auth_token` cookie; X_CT0 optional). It is placed in the browser's cookie jar only: never logged,
// never written to disk, never committed.
// Exit codes: 0 captured, 2 usage, 3 auth failed, 4 blocked by X (challenge / rate limit / login wall).
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { createRequire } from 'node:module';
import { ROOT, TOOL_VERSION, accountDir, readJson, writeJson, snowflakeDate, parseArgs, HANDLE_RE } from './lib/util.mjs';

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
const SURFACE_URL = { posts: h => `https://x.com/${h}`, replies: h => `https://x.com/${h}/with_replies`, media: h => `https://x.com/${h}/media` };
for (const s of surfaces) if (!SURFACE_URL[s]) { console.error(`unknown surface: ${s}`); process.exit(2); }

const runId = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
const runDir = path.join(dir, 'raw', runId);
fs.mkdirSync(runDir, { recursive: true });
const rawFile = path.join(runDir, 'articles.jsonl');
const extractSrc = fs.readFileSync(path.join(ROOT, 'tools/xmap/extract.js'), 'utf8');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const jitter = (lo, hi) => lo + Math.random() * (hi - lo);
const log = (...a) => console.log(`[xmap ${new Date().toISOString().slice(11, 19)}]`, ...a);

const token = process.env.X_AUTH_TOKEN || '';
if (!token && !args['allow-logged-out']) {
  console.error('auth_failed: X_AUTH_TOKEN is not set. See docs/SETUP.md, or pass --allow-logged-out for the few posts X shows without a session.');
  process.exit(3);
}

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
let netN = 0;
page.on('response', async r => {
  try {
    const u = new URL(r.url());
    if (!/(^|\.)x\.com$/.test(u.hostname) || !/graphql/.test(u.pathname) || netN >= 400) return;
    const body = await r.body();
    if (body.length < 300) return;
    fs.mkdirSync(path.join(runDir, 'net'), { recursive: true });
    fs.writeFileSync(path.join(runDir, 'net', `${String(netN++).padStart(4, '0')}-${u.pathname.split('/').pop().replace(/\W/g, '')}.json.gz`), zlib.gzipSync(body));
  } catch { /* response body unavailable (navigation, cache): not an error */ }
});

const manifest = {
  run_id: runId, handle, tool_version: TOOL_VERSION, started_at: new Date().toISOString(), ended_at: null,
  auth: 'none', browser: `chromium ${browser.version()} headed`, since: sinceStr, max_posts: maxPosts,
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
    log('signed-in session confirmed');
  } else log('running WITHOUT a session: X shows only a handful of posts');

  const seen = new Set();
  const deadline = Date.now() + maxMinutes * 60000;
  let seq = 0;
  for (const surface of surfaces) {
    const url = SURFACE_URL[surface](handle);
    const rec = { surface, url, steps: 0, new_posts: 0, stop_reason: '' };
    manifest.surfaces.push(rec);
    log(`surface=${surface} ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('article', { timeout: 30000 }).catch(() => {});
    await sleep(jitter(2500, 4500));
    let stale = 0; const recentOwn = [];
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
      if (seen.size >= maxPosts) { rec.stop_reason = 'max_posts'; break; }
      if (Date.now() > deadline) { rec.stop_reason = 'max_minutes'; break; }
      if (stale >= 6) { rec.stop_reason = s.signals.signin_wall ? 'signin_wall' : s.signals.error ? 'page_error' : 'end_of_timeline'; break; }
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
  const todo = [...new Map(clipped.map(p => [p.id, p])).values()].slice(0, Number(cap.max_permalinks ?? 60));
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
