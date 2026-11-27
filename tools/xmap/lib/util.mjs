import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

export const ROOT = process.env.XMAP_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const TOOL_VERSION = '1.2.0';
export const HANDLE_RE = /^[A-Za-z0-9_]{1,15}$/;

// X post IDs are snowflakes since 2010-11-04: the high bits are milliseconds since the Twitter epoch.
// This gives an exact UTC creation time without depending on the relative dates the UI displays ("3h", "Nov 26").
const TW_EPOCH = 1288834974657n;
const FIRST_SNOWFLAKE = 27000000000000000n;
export function snowflakeDate(id) {
  const n = BigInt(id);
  if (n < FIRST_SNOWFLAKE) return null; // pre-snowflake sequential ID: creation time is not encoded
  return new Date(Number((n >> 22n) + TW_EPOCH));
}
export const cmpIdDesc = (a, b) => { const x = BigInt(a), y = BigInt(b); return x === y ? 0 : x > y ? -1 : 1; };

// "11 replies, 35 reposts, 547 likes, 124 bookmarks, 135384 views" -> exact integers.
// Signed-in labels also carry the viewer's own state ("82 likes, Liked, 1 bookmark"): a count must start with a
// digit and the keyword must end at a word boundary, or ", Liked" would read as a like count of 0.
export function parseMetrics(label) {
  const out = {};
  for (const m of (label || '').matchAll(/(\d[\d,.]*)\s+(repl(?:y|ies)|reposts?|likes?|bookmarks?|views?|quotes?)\b/gi)) {
    const key = { rep: 'replies', repo: 'reposts', lik: 'likes', boo: 'bookmarks', vie: 'views', quo: 'quotes' }[
      /^repo/i.test(m[2]) ? 'repo' : m[2].slice(0, 3).toLowerCase()];
    out[key] = Number(m[1].replace(/[,.]/g, ''));
  }
  return out;
}

export function accountDir(handle) {
  if (!HANDLE_RE.test(handle)) throw new Error(`invalid handle: ${handle}`);
  return path.join(ROOT, 'accounts', handle.toLowerCase());
}
export const readJson = (f, dflt) => (fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : dflt);
export const writeJson = (f, o) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, JSON.stringify(o, null, 2) + '\n'); };
export function readJsonl(f) {
  if (!fs.existsSync(f)) return [];
  const buf = fs.readFileSync(f);
  const txt = f.endsWith('.gz') ? zlib.gunzipSync(buf).toString('utf8') : buf.toString('utf8');
  return txt.split('\n').filter(Boolean).map(l => JSON.parse(l));
}
export const writeJsonl = (f, rows) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, rows.map(r => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : '')); };
export function parseArgs(argv, spec = {}) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) { const k = a.slice(2); if (spec[k] === 'bool') out[k] = true; else out[k] = argv[++i]; } else out._.push(a);
  }
  return out;
}

// GraphQL operations capture may store under raw/<run>/net/: only responses about the target profile and its posts.
// Everything else the signed-in page loads (HomeTimeline, sidebar recommendations, trends, pinned lists, Grok
// account JWTs) belongs to the operator's session, not to the account, and carries credentials or private feed data.
export const NET_KEEP = new Set([
  'UserByScreenName', 'UserByRestId', 'ProfileSpotlightsQuery',
  'UserTweets', 'UserOriginalsTimeline', 'UserTweetsAndReplies', 'UserMedia', 'UserHighlightsTweets',
  'TweetDetail', 'TweetResultByRestId', 'TweetResultsByRestIds', 'SmartTagAttachmentQuery',
]);
export const netOperationKept = op => NET_KEEP.has(op);
