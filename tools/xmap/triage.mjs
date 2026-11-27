#!/usr/bin/env node
// xmap triage: the operator's relevance rule, applied per post -> accounts/<handle>/triage.jsonl
//   node tools/xmap/triage.mjs <handle>
// One line per post in posts.jsonl (same order): {"id","keep","reason"}. posts.jsonl and raw/ are never touched.
//
// A post is skipped when its own words (URLs and @mentions removed) carry no claim, position, prediction, number,
// ticker, link commentary or self-disclosure. A quote post whose own words are filler is skipped even when the quoted
// post has content. Decisions come from two layers:
//   1. a deterministic first pass (below), which keeps or skips the clear cases and marks the rest `review`;
//   Exception: a quote whose own words only endorse or reject the quoted post ("cosigned", "he's right", "🎯", "wrong")
//   goes to review, because it is kept when the quoted post carries a forecast, claim or position.
//   2. accounts/<handle>/triage_overrides.jsonl, one {"id","keep","reason"} per judged post. Overrides decide every
//      review post and may reverse a first-pass decision on reading. A review post with no override is skipped and
//      counted as unjudged, so an incomplete judgment pass is visible rather than silent.
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJsonl, writeJsonl, parseArgs } from './lib/util.mjs';

const URL_RE = /https?:\/\/\S+/g;
const MENTION_RE = /(?<![A-Za-z0-9_])@[A-Za-z0-9_]{1,15}/g;
// Stock phrases that carry no content of their own, matched against the whole of the post's own words.
export const FILLER = new RegExp('^(' + [
  "requesting more of this on (the|my) timeline[,! ]*(forever)?", 'more of this on (the|my) timeline( forever)?',
  'what a time to be alive', 'you absolutely love to see it', "(he|she|they)('s| is| are)? (so )?right( as usual)?",
  'cosigned( omg)?', 'unconditionally endorsed', '(hard |can )?vouch', 'real( btw)?', 'based', 'this', 'lol', 'lmao', 'omg',
  'wow', 'absurd', 'crazy', 'beautiful', 'bullish', "let'?s go+", 'me and who', 'underrated tweet', 'worth reading',
  'probably worth reading', "you can'?t stop this train", 'golden age of media coming in hott', "it'?s good", 'this is the way',
  'and so it begins', 'it has begun', 'somehow real', 'absolutely real', 'absolutely unequivocally correct', 'correct',
  'agreed', 'true', 'facts', 'same', 'mood', 'yes', 'no', 'welcome', 'congrats', 'huge congrats', 'bless', 'god bless',
  'amazing', 'incredible', 'gorgeous', 'perfect', "she'?s perfect", "he'?s perfect", 'generational talent', 'interesting',
  'signal boo+st', "let'?s gooo+", 'hero', '1\\) what', 'aaa+h+', 'ahh+', 'eee+', 'wheee+', 'best timeline',
  'unconditionally free', 'absurd returns',
].join('|') + ')$', 'iu');

// Endorsement or rejection of the quoted post, and nothing else (operator exception, 2026-11-27): such a quote is
// kept when the quoted post carries a forecast, claim or position, so it goes to review instead of being auto-skipped.
export const ENDORSE = new RegExp('^\\W*(' + [
  '(un(conditionally|qualified)\\s*)?(co-?signed|endorsed)', "(he|she|they)('s| is| are)?( so| dead| absolutely| more)? right( btw| as usual| than not( tbh)?)?",
  '(absolutely |dead |unequivocally )*(correct|right)', 'agreed', 'true', 'so true', 'facts', '(somehow |absolutely )?real( btw)?', 'based', 'this',
  'exactly', '100%', '\\+1', 'yes+', 'this is the way', '(hard |can )?vouch', 'fact check: true', "when you're right,? you're right",
  'and they were dead right', "(tweets|takes)( that| i)? will (continue to |unfortunately )?age (unbelievably |very |\\*very\\* )?well",
  'this will age (unbelievably |very )?well', 'i believe this( fwiw)?', '(he|she|this guy) gets it',
].join('|') + ')\\W*$', 'iu');
export const REJECT = /^\W*(dead wrong|wrong|lol no|no|nope|cope|fake news|false|not true|incorrect|doubt it)\W*$/iu;
const AGREE_EMOJI = /^[\s🎯💯✅👆☝️🤝]+$/u;
const endorsementShaped = (p, t) => !!(p.quoted && p.quoted.handle && (p.quoted.text || '').trim() && !p.quoted.unavailable)
  && (ENDORSE.test(t) || REJECT.test(t) || (t && AGREE_EMOJI.test(t)));

const core = t => (t || '').replace(URL_RE, ' ').replace(MENTION_RE, ' ').replace(/\s+/g, ' ').trim();
const words = t => t.match(/[A-Za-z0-9$%']+/g) || [];

// First pass: { decision: 'keep' | 'skip' | 'review', reason }.
export function firstPass(p) {
  const t = core(p.text), w = words(t);
  const contentLinks = (p.links || []).filter(l => !/^https:\/\/(x|twitter)\.com\//.test(l));
  const norm = t.toLowerCase().replace(/[^\p{L}\p{N}_' )]+/gu, '').trim();
  const bare = t.replace(/[^\p{L}\p{N}_$%]+/gu, ' ').trim().toLowerCase().replace(/^[!?. ]+|[!?. ]+$/g, '');
  if (p.kind === 'repost') return { decision: 'skip', reason: "repost: not the account's own words" };
  if (endorsementShaped(p, t)) return { decision: 'review', reason: 'review: endorsement or rejection of the quoted post' };
  if ((p.cashtags || []).length) return { decision: 'keep', reason: 'auto: ticker' };
  if (!w.length && !contentLinks.length) return { decision: 'skip', reason: 'auto: no own words (media/emoji/link only)' };
  if (FILLER.test(norm) || FILLER.test(bare)) return { decision: 'skip', reason: 'auto: stock filler phrase' };
  if (w.length <= 2 && !/\d/.test(t) && !contentLinks.length) return { decision: 'skip', reason: 'auto: bare reaction (<=2 words)' };
  if (w.length >= 14) return { decision: 'keep', reason: 'auto: substantive length' };
  if (contentLinks.length && w.length >= 3) return { decision: 'keep', reason: 'auto: link with commentary' };
  return { decision: 'review', reason: `review: ${w.length} words` };
}

export function triage(handle) {
  const dir = accountDir(handle);
  const posts = readJsonl(path.join(dir, 'posts.jsonl'));
  const overrides = new Map(readJsonl(path.join(dir, 'triage_overrides.jsonl')).map(o => [o.id, o]));
  const ids = new Set(posts.map(p => p.id));
  const counts = { keep: 0, skip: 0, auto: 0, judged: 0, unjudged: 0, review: 0 };
  const rows = posts.map(p => {
    const f = firstPass(p), o = overrides.get(p.id);
    if (f.decision === 'review') counts.review++;
    let row;
    if (o) { row = { id: p.id, keep: !!o.keep, reason: `judged ${o.keep ? 'keep' : 'skip'}: ${o.reason}` }; counts.judged++; }
    else if (f.decision === 'review') { row = { id: p.id, keep: false, reason: 'review: not judged (skipped by default)' }; counts.unjudged++; }
    else { row = { id: p.id, keep: f.decision === 'keep', reason: f.reason }; counts.auto++; }
    counts[row.keep ? 'keep' : 'skip']++;
    return row;
  });
  writeJsonl(path.join(dir, 'triage.jsonl'), rows);
  const stale = [...overrides.keys()].filter(id => !ids.has(id));
  return { handle, posts: posts.length, ...counts, stale_overrides: stale.length };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2), { review: 'bool' });
  if (!a._[0]) { console.error('usage: triage.mjs <handle> [--review]   (--review lists unjudged review posts)'); process.exit(2); }
  const handle = a._[0].replace(/^@/, '');
  const r = triage(handle);
  console.log(`triage handle=${r.handle} posts=${r.posts} kept=${r.keep} skipped=${r.skip} auto=${r.auto} judged=${r.judged} review=${r.review} unjudged=${r.unjudged} stale_overrides=${r.stale_overrides}`);
  if (a.review) {
    const dir = accountDir(handle);
    const t = new Map(readJsonl(path.join(dir, 'triage.jsonl')).map(x => [x.id, x]));
    for (const p of readJsonl(path.join(dir, 'posts.jsonl'))) if (t.get(p.id).reason.startsWith('review:')) console.log(`${p.id}\t${p.kind}\t${core(p.text).slice(0, 140)}`);
  }
  process.exit(r.unjudged ? 1 : 0);
}
