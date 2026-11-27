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
const { snowflakeDate, parseMetrics, cmpIdDesc, netOperationKept } = await import('../tools/xmap/lib/util.mjs');
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
  // Signed-in: the viewer's own Liked/Reposted/Bookmarked state sits between the counts.
  assert.deepEqual(parseMetrics('3 replies, 1 repost, 82 likes, Liked, 1 bookmark, 2448 views'), { replies: 3, reposts: 1, likes: 82, bookmarks: 1, views: 2448 });
  assert.deepEqual(parseMetrics('2 reposts, Reposted, 145 likes, Liked, 12 bookmarks, Bookmarked, 6730 views'), { reposts: 2, likes: 145, bookmarks: 12, views: 6730 });
});

test('entities', () => {
  const e = entities('long $NVDA and $brk.b vs @Austen, not a@b.com #AI costs $20');
  assert.deepEqual(e.cashtags, ['NVDA', 'BRK.B']);
  assert.deepEqual(e.mentions, ['austen']);
  assert.deepEqual(e.hashtags, ['ai']);
});

// Render a saved page at its x.com URL (so relative links resolve as on X) with every other request aborted.
async function extractFixture(file) {
  const { chromium } = createRequire(import.meta.url)('playwright');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.route('**/*', r => (r.request().url().startsWith('https://x.com/astridwilde') ? r.fulfill({ contentType: 'text/html; charset=utf-8', body: fs.readFileSync(path.join(here, 'fixtures', file), 'utf8') }) : r.abort()));
  await page.goto('https://x.com/astridwilde');
  const snap = await page.evaluate(fs.readFileSync(path.join(here, '../tools/xmap/extract.js'), 'utf8'));
  await browser.close();
  return snap;
}

let snapshot;
test('extractor reads the real profile markup', async () => {
  snapshot = await extractFixture('profile-logged-out.html');

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

test('normalize -> stats -> validate, including map citation and quotation checks', async () => {
  const dir = path.join(tmp, 'accounts', 'astridwilde');
  const mkRun = (runId, rows, auth = 'session') => {
    const rd = path.join(dir, 'raw', runId); fs.mkdirSync(rd, { recursive: true });
    fs.writeFileSync(path.join(rd, 'articles.jsonl.gz'), zlib.gzipSync(rows.map((p, i) => JSON.stringify({ run_id: runId, surface: 'posts', seq: i, captured_at: '2026-11-27T10:00:00.000Z', ...p })).join('\n')));
    fs.writeFileSync(path.join(rd, 'run.json'), JSON.stringify({ run_id: runId, handle: 'astridwilde', status: 'ok', auth, posts_captured: rows.length, since: '2026-08-29', profile: snapshot.profile, surfaces: [{ surface: 'posts', stop_reason: 'reached_since' }] }));
  };
  mkRun('20261127T100000Z', snapshot.posts);
  let r = await normalize('astridwilde');
  assert.equal(r.posts, 5);
  // A second run re-observing the same posts is an idempotent upsert, and a clipped re-observation never replaces full text.
  mkRun('20261127T110000Z', [{ ...snapshot.posts[0], text: 'do less', truncated: true }]);
  r = await normalize('astridwilde');
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

// Signed-in X renders quotes as [role=link] cards with no nested article and no permalink, puts social context
// inside the article's single wrapper, and gives t.co anchors no title. Extractor 1.0.0 read every one of these
// posts as a plain post (run 20261127T101916Z: 508 rows, 0 quotes, against 379 quotes in the page's own API data).
let signedIn;
test('extractor reads the signed-in timeline markup', async () => {
  signedIn = await extractFixture('profile-signed-in.html');
  const by = Object.fromEntries(signedIn.posts.map(p => [p.id, p]));
  assert.equal(signedIn.posts.length, 10);
  assert.ok(signedIn.posts.every(p => p.handle === 'astridwilde' && p.name === 'Astrid Wilde 🌞'));

  assert.equal(by['1926763616964899185'].context, 'Pinned');
  assert.ok(signedIn.posts.filter(p => p.id !== '1926763616964899185').every(p => p.context === ''));

  // Quote card: the quoted post's author, time, text and media belong to `quoted`, not to the quoting post.
  const q = by['2126204678702792894'];
  assert.equal(q.text, 'me and who');
  assert.deepEqual(q.media, []);
  assert.equal(q.quoted.handle, 'equine__dentist');
  assert.equal(q.quoted.name, 'horse dentist');
  assert.equal(q.quoted.text, 'can i come over and bother you like this');
  assert.equal(q.quoted.created_at, '2026-11-27T01:01:00.000Z');
  assert.equal(q.quoted.media[0].type, 'video');
  assert.equal(q.quoted.id, null, 'a signed-in quote card carries no permalink');

  // "Replying to" inside a quote card describes the quoted post.
  const qr = by['2121320982778724718'];
  assert.deepEqual(qr.replying_to, []);
  assert.deepEqual(qr.quoted.replying_to, ['astridwilde', 'XtineFang']);

  // Community-note links on a quoted post are neither the account's links nor the quoted author's.
  const noted = by['2121100560640491939'];
  assert.deepEqual(noted.links, []);
  assert.deepEqual(noted.quoted.links, []);
  assert.equal(noted.quoted.handle, 'zack_overflow');

  // Quote of a quote: the inner preview is nested, not merged into the quoted text.
  const qq = by['2125440798909251770'];
  assert.equal(qq.quoted.handle, 'KyleAdamsStocks');
  assert.doesNotMatch(qq.quoted.text, /FinX/);
  assert.equal(qq.quoted.quoted.handle, 'siyul');
  assert.match(qq.text, /accumulating \$QURE doesn't seem dumb/);

  // Unavailable quoted post (bare nested article) and an in-site link in the text.
  const un = by['2122027924832616721'];
  assert.deepEqual(un.quoted, { unavailable: true, text: 'This post is unavailable.' });
  assert.match(un.text, /thx +https:\/\/x\.com\/Xintuihao\/status\/2060198995067359521$/);
  assert.deepEqual(un.links.map(l => l.url), ['https://x.com/Xintuihao/status/2060198995067359521']);
  assert.equal(un.media.length, 4);

  // t.co in text stays t.co in the DOM read (no title signed-in); X's policy-label links are never links.
  assert.equal(by['2115235119292469400'].text, 'opt out at https://t.co/f1um7Ge4ru');
  assert.ok(signedIn.posts.every(p => [...p.links, ...((p.quoted && p.quoted.links) || [])].every(l => !/help\.x\.com/.test(l.url))));
  assert.equal(by['2112010612159156714'].quoted.handle, 'adriasmonica');
});

test('normalize re-reads stale rows from raw_html and fills gaps from the run\'s API responses', async () => {
  const dir = path.join(tmp, 'accounts', 'signedin');
  const runId = '20261127T101916Z', rd = path.join(dir, 'raw', runId);
  fs.mkdirSync(path.join(rd, 'net'), { recursive: true });
  // Rows as extractor 1.0.0 recorded them from this markup: no quote, no name, no context.
  const stale = signedIn.posts.map((p, i) => ({ run_id: runId, surface: 'posts', seq: i, captured_at: '2026-11-27T10:20:00.000Z', extractor_version: '1.0.0', ...p, handle: 'signedin', name: '', context: '', quoted: null, raw_html: p.raw_html.replaceAll('astridwilde', 'signedin') }));
  fs.writeFileSync(path.join(rd, 'articles.jsonl.gz'), zlib.gzipSync(stale.map(r => JSON.stringify(r)).join('\n')));
  fs.writeFileSync(path.join(rd, 'run.json'), JSON.stringify({ run_id: runId, handle: 'signedin', status: 'ok', auth: 'session', posts_captured: stale.length, since: '2026-08-29', profile: { ...snapshot.profile, handle: 'signedin' }, surfaces: [{ surface: 'posts', stop_reason: 'reached_since' }] }));
  fs.writeFileSync(path.join(rd, 'net', '0001-UserByScreenName.json.gz'), zlib.gzipSync(fs.readFileSync(path.join(here, 'fixtures/net-UserByScreenName.json'), 'utf8').replaceAll('"astridwilde"', '"signedin"')));
  fs.writeFileSync(path.join(rd, 'net', '0000-UserOriginalsTimeline.json.gz'), zlib.gzipSync(fs.readFileSync(path.join(here, 'fixtures/net-UserOriginalsTimeline.json'), 'utf8').replaceAll('"astridwilde"', '"signedin"')));

  const r = await normalize('signedin');
  assert.equal(r.reparsed, 10);
  const posts = Object.fromEntries(fs.readFileSync(path.join(dir, 'posts.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l)).map(p => [p.id, p]));
  assert.equal(posts['1926763616964899185'].pinned, true);
  assert.equal(posts['2126204678702792894'].kind, 'quote');
  assert.equal(posts['2126204678702792894'].author_name, 'Astrid Wilde 🌞');
  // Quoted id from the API record; the card text stays what the page showed.
  assert.equal(posts['2126204678702792894'].quoted.id, '2126119062161805803');
  assert.equal(posts['2126204678702792894'].quoted.url, 'https://x.com/equine__dentist/status/2126119062161805803');
  assert.equal(posts['2126204678702792894'].quoted.text, 'can i come over and bother you like this');
  assert.equal(posts['2122027924832616721'].quoted.unavailable, true);
  assert.equal(posts['2122027924832616721'].quoted.id, '2060198995067359521');
  // t.co expanded; a link card's hidden URL recovered; self-thread continuations are replies.
  assert.equal(posts['2115235119292469400'].text, 'opt out at https://redact.dev');
  assert.deepEqual(posts['2115235119292469400'].links, ['https://redact.dev']);
  assert.deepEqual(posts['2122108846810505404'].links, ['https://youtu.be/ZOfbixoufTU']);
  assert.equal(posts['2124430544822034647'].kind, 'reply');
  assert.deepEqual(posts['2124430544822034647'].replying_to, ['signedin']);
  assert.equal(posts['2124430544822034647'].in_reply_to_id, '2124429042900521400');

  // Profile: the page's own user record wins over the DOM header read (which 1.0.0 got wrong signed-in).
  const prof = JSON.parse(fs.readFileSync(path.join(dir, 'profile.json'), 'utf8'));
  assert.equal(prof.source, 'api');
  assert.equal(prof.name, 'Astrid Wilde 🌞');
  assert.equal(prof.user_id, '52549030');
  assert.equal(prof.bio, 'male ☼ we will end human menial labor this decade ☼');
  assert.equal(prof.website.url, 'https://inheritance.ai');
  assert.equal(prof.joined, 'Joined June 2009');
  assert.equal(prof.followers, '20,037');
  assert.equal(prof.posts_count, '42,007 posts');

  const s = stats('signedin');
  assert.deepEqual(s.by_kind, { post: 1, quote: 7, reply: 2 });
  assert.equal(s.top_domains.find(d => d.key === 'youtu.be').n, 1);
  assert.deepEqual(validate('signedin').filter(x => !x.ok).map(x => x.name), []);
});

test('capture stores only target-profile API responses, never operator-session ones', () => {
  for (const op of ['UserByScreenName', 'UserOriginalsTimeline', 'UserTweets', 'TweetDetail', 'ProfileSpotlightsQuery']) assert.ok(netOperationKept(op), op);
  for (const op of ['grokAccountJwtQuery', 'HomeTimeline', 'SidebarUserRecommendations', 'ExploreSidebar', 'PinnedTimelines', 'useStoryTopicQuery']) assert.ok(!netOperationKept(op), op);
  const src = fs.readFileSync(path.join(here, '..', 'tools', 'xmap', 'capture.mjs'), 'utf8');
  assert.match(src, /if \(!netOperationKept\(op\)\) return;/);
});
