import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'xmap-test-'));
process.env.XMAP_ROOT = tmp; // isolate accounts/ for this test process
const { snowflakeDate, parseMetrics, cmpIdDesc } = await import('../tools/xmap/lib/util.mjs');
const { normalize, entities } = await import('../tools/xmap/normalize.mjs');
const { stats } = await import('../tools/xmap/stats.mjs');
const { validate, MAP_SECTIONS } = await import('../tools/xmap/validate.mjs');

test('snowflake id -> exact UTC time; pre-snowflake ids yield null', () => {
  assert.equal(snowflakeDate('1926763616964899185').toISOString().slice(0, 10), '2025-05-25');
  assert.equal(snowflakeDate('20'), null);
  assert.ok(cmpIdDesc('2126204678702792894', '1926763616964899185') < 0);
});

test('metrics label -> exact integers', () => {
  assert.deepEqual(parseMetrics('11 replies, 35 reposts, 547 likes, 124 bookmarks, 135384 views'), { replies: 11, reposts: 35, likes: 547, bookmarks: 124, views: 135384 });
  assert.deepEqual(parseMetrics('1 reply, 1 repost, 1 like, 1,204 views'), { replies: 1, reposts: 1, likes: 1, views: 1204 });
  assert.deepEqual(parseMetrics(''), {});
});

test('entities', () => {
  const e = entities('long $NVDA and $brk.b vs @Austen, not a@b.com #AI costs $20');
  assert.deepEqual(e.cashtags, ['NVDA', 'BRK.B']);
  assert.deepEqual(e.mentions, ['austen']);
  assert.deepEqual(e.hashtags, ['ai']);
});

let snapshot;
test('extractor reads the real profile markup', async () => {
  const { chromium } = createRequire(import.meta.url)('playwright');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.route('**/*', r => (r.request().url().startsWith('https://x.com/astridwilde') ? r.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(here, 'fixtures/profile-logged-out.html'), 'utf8') }) : r.abort()));
  await page.goto('https://x.com/astridwilde');
  snapshot = await page.evaluate(fs.readFileSync(path.join(here, '../tools/xmap/extract.js'), 'utf8'));
  await browser.close();

  assert.equal(snapshot.profile.handle, 'astridwilde');
  assert.equal(snapshot.profile.user_id, '52549030');
  assert.equal(snapshot.profile.joined, 'Joined June 2009');
  assert.equal(snapshot.profile.location, 'San Francisco, CA');
  assert.equal(snapshot.profile.website.text, 'inheritance.ai');
  assert.match(snapshot.profile.bio, /menial labor/);
  assert.equal(snapshot.profile.following, '8,273');
  assert.equal(snapshot.posts.length, 5, 'top-level posts only; quoted posts are nested');

  const pinned = snapshot.posts[0];
  assert.equal(pinned.id, '1926763616964899185');
  assert.equal(pinned.context, 'Pinned');
  assert.equal(pinned.text, 'do less\n\ndo it well\n\ndo it for a long time');
  assert.match(pinned.metrics_label, /547 likes/);
  assert.equal(pinned.quoted, null);

  const quote = snapshot.posts[2];
  assert.equal(quote.text, 'real btw');
  assert.equal(quote.quoted.handle, 'MingfeiGuo');
  assert.match(quote.quoted.text, /https:\/\/github\.com\/guoriyue\/z123/, 't.co links expand to the real URL');
  assert.equal(snapshot.posts[1].quoted.media[0].type, 'video');
  assert.ok(snapshot.posts.every(p => p.handle === 'astridwilde' && p.raw_html.startsWith('<article')));
});

test('normalize -> stats -> validate, including map citation and quotation checks', () => {
  const dir = path.join(tmp, 'accounts', 'astridwilde');
  const mkRun = (runId, rows, auth = 'session') => {
    const rd = path.join(dir, 'raw', runId); fs.mkdirSync(rd, { recursive: true });
    fs.writeFileSync(path.join(rd, 'articles.jsonl.gz'), zlib.gzipSync(rows.map((p, i) => JSON.stringify({ run_id: runId, surface: 'posts', seq: i, captured_at: '2026-11-27T10:00:00.000Z', ...p })).join('\n')));
    fs.writeFileSync(path.join(rd, 'run.json'), JSON.stringify({ run_id: runId, handle: 'astridwilde', status: 'ok', auth, posts_captured: rows.length, since: '2026-08-29', profile: snapshot.profile, surfaces: [{ surface: 'posts', stop_reason: 'reached_since' }] }));
  };
  mkRun('20261127T100000Z', snapshot.posts);
  let r = normalize('astridwilde');
  assert.equal(r.posts, 5);
  // A second run re-observing the same posts is an idempotent upsert, and a clipped re-observation never replaces full text.
  mkRun('20261127T110000Z', [{ ...snapshot.posts[0], text: 'do less', truncated: true }]);
  r = normalize('astridwilde');
  assert.equal(r.posts, 5);
  const posts = fs.readFileSync(path.join(dir, 'posts.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
  const pinned = posts.find(p => p.id === '1926763616964899185');
  assert.equal(pinned.text, 'do less\n\ndo it well\n\ndo it for a long time');
  assert.equal(pinned.created_at.slice(0, 10), '2025-05-25');
  assert.deepEqual(pinned.runs, ['20261127T100000Z', '20261127T110000Z']);
  assert.equal(posts.filter(p => p.kind === 'quote').length, 4);
  assert.equal(pinned.metrics.views, 135384);

  const s = stats('astridwilde');
  assert.equal(s.posts_total, 5);
  assert.equal(s.top_quoted_authors.length, 4);
  assert.equal(s.top_domains[0].key, 'github.com');
  let res = validate('astridwilde');
  assert.deepEqual(res.filter(x => !x.ok).map(x => x.name), []);

  const sections = MAP_SECTIONS.map(h => `## ${h}\n\nClaim grounded in a post [p:1926763616964899185].\n`).join('\n');
  const good = `# @astridwilde\n<!-- xmap: posts=5 run=20261127T110000Z -->\n\n${sections}\n> "do it well [...] do it for a long time" [p:1926763616964899185]\n`;
  fs.writeFileSync(path.join(dir, 'map.md'), good);
  assert.deepEqual(validate('astridwilde').filter(x => !x.ok).map(x => x.name), []);

  fs.writeFileSync(path.join(dir, 'map.md'), good.replace('posts=5', 'posts=4') + '\n> "do more" [p:1926763616964899185]\nInvented [p:111].\n');
  assert.deepEqual(validate('astridwilde').filter(x => !x.ok).map(x => x.name), ['map.dataset_stamp_current', 'map.citations_resolve', 'map.quotes_verbatim']);
});
