// Facts the signed-in DOM does not carry, read from the GraphQL responses the profile page itself requested
// (stored passively by capture under raw/<run>/net/). The DOM stays the primary record; these only fill gaps:
//   - the quoted post's id (a signed-in quote card has no permalink),
//   - the expanded target of each t.co link (signed-in anchors carry no title with the full URL),
//   - URLs X hides from the text and shows only as a link card,
//   - the reply parent of self-thread continuations (the profile shows no "Replying to" for those).
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const tweetOf = o => (o && o.__typename === 'TweetWithVisibilityResults' ? o.tweet : o);
const isTweet = o => o && o.__typename === 'Tweet' && o.rest_id && o.legacy;
const screenName = t => {
  const u = t.core && t.core.user_results && t.core.user_results.result;
  return (u && ((u.core && u.core.screen_name) || (u.legacy && u.legacy.screen_name))) || null;
};
function info(t) {
  const L = t.legacy;
  const note = t.note_tweet && t.note_tweet.note_tweet_results && t.note_tweet.note_tweet_results.result;
  const urls = [...((L.entities && L.entities.urls) || []), ...((note && note.entity_set && note.entity_set.urls) || [])]
    .filter(u => u.url && u.expanded_url).map(u => ({ url: u.url, expanded: u.expanded_url }));
  const q = tweetOf(t.quoted_status_result && t.quoted_status_result.result);
  return {
    id: t.rest_id, handle: screenName(t), urls,
    in_reply_to_id: L.in_reply_to_status_id_str || null, in_reply_to: L.in_reply_to_screen_name || null,
    quoted_id: L.quoted_status_id_str || (isTweet(q) ? q.rest_id : null),
    quoted: isTweet(q) ? info(q) : null,
  };
}

// id -> info, over every net/ response of the given run directories (later runs win).
export function loadNet(runDirs) {
  const byId = new Map();
  const walk = o => {
    if (Array.isArray(o)) { o.forEach(walk); return; }
    if (!o || typeof o !== 'object') return;
    const t = tweetOf(o);
    if (isTweet(t)) byId.set(t.rest_id, info(t));
    for (const v of Object.values(o)) walk(v);
  };
  for (const d of runDirs) {
    const net = path.join(d, 'net');
    if (!fs.existsSync(net)) continue;
    for (const f of fs.readdirSync(net).filter(f => f.endsWith('.json.gz')).sort()) {
      try { walk(JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(net, f))).toString('utf8'))); } catch { /* not JSON: skip */ }
    }
  }
  return byId;
}

// The account's profile as the page's own UserByScreenName response records it (exact counts, expanded website),
// in the same shape parseProfile produces from the DOM. null when the run holds no such response.
export function loadProfile(runDir, handle) {
  const net = path.join(runDir, 'net');
  if (!fs.existsSync(net)) return null;
  let found = null;
  for (const f of fs.readdirSync(net).filter(f => /UserByScreenName\.json\.gz$/.test(f)).sort()) {
    try {
      const u = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(net, f))).toString('utf8')).data.user.result;
      if (u && u.core && u.core.screen_name && u.core.screen_name.toLowerCase() === handle.toLowerCase()) found = u;
    } catch { /* not a user record: skip */ }
  }
  if (!found) return null;
  const u = found, bio = u.profile_bio || {}, n = x => (x == null ? null : Number(x).toLocaleString('en-US'));
  const site = ((bio.entities && bio.entities.url && bio.entities.url.urls) || [])[0];
  const joined = u.core.created_at ? new Date(u.core.created_at) : null;
  return {
    handle: u.core.screen_name, name: u.core.name, user_id: u.rest_id || null,
    verified: !!u.is_blue_verified, bio: expand(bio.description || '', ((bio.entities && bio.entities.description && bio.entities.description.urls) || []).map(x => ({ url: x.url, expanded: x.expanded_url }))),
    location: (u.location && u.location.location) || '',
    website: site ? { text: site.display_url, via: site.url, url: site.expanded_url } : null,
    joined: joined ? `Joined ${joined.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })}` : null,
    following: n(u.relationship_counts && u.relationship_counts.following),
    followers: n(u.relationship_counts && u.relationship_counts.followers),
    posts_count: u.tweet_counts && u.tweet_counts.tweets != null ? `${n(u.tweet_counts.tweets)} posts` : null,
    avatar: u.avatar && u.avatar.image_url ? u.avatar.image_url.replace(/_normal(\.\w+)$/, '_400x400$1') : null,
    banner: u.banner && u.banner.image_url ? `${u.banner.image_url}/1500x500` : null,
    pinned: (u.pinned_items && u.pinned_items.tweet_ids_str) || [],
    source: 'api',
  };
}

const expand = (s, urls) => urls.reduce((acc, u) => acc.split(u.url).join(u.expanded), s || '');
const expandLinks = (links, urls, text) => {
  const out = (links || []).map(l => {
    const hit = urls.find(u => u.url === l.url || u.url === l.via);
    return hit ? { ...l, url: hit.expanded } : l;
  });
  // URLs X hides from the displayed text (a link card's URL) still belong to the post.
  for (const u of urls) if (!out.some(l => l.url === u.expanded) && !(text || '').includes(u.expanded)) out.push({ url: u.expanded, via: u.url, text: '', in_text: false, from: 'net' });
  return out;
};
const sameHandle = (a, b) => !a || !b || a.toLowerCase() === b.toLowerCase();

// Returns the raw row with gaps filled from its API record; the row is returned unchanged when there is none.
export function enrich(raw, net) {
  const n = net.get(raw.id);
  if (!n || !sameHandle(n.handle, raw.handle)) return raw;
  const out = { ...raw, text: expand(raw.text, n.urls) };
  out.links = expandLinks(raw.links, n.urls, out.text);
  if (!(raw.replying_to || []).length && n.in_reply_to) out.replying_to = [n.in_reply_to];
  out.in_reply_to_id = n.in_reply_to_id;
  const q = raw.quoted;
  if (q && !q.ref && n.quoted_id && (q.unavailable || sameHandle(q.handle, n.quoted && n.quoted.handle))) {
    const qn = n.quoted || { urls: [] };
    out.quoted = { ...q, id: q.id || n.quoted_id, handle: q.handle || qn.handle || null };
    if (!q.unavailable) { out.quoted.text = expand(q.text, qn.urls); out.quoted.links = expandLinks(q.links, qn.urls, out.quoted.text); }
  } else if (!q && n.quoted && n.quoted_id) {
    // The page rendered no quote card for a post the API records as a quote.
    out.quoted = { id: n.quoted_id, handle: n.quoted.handle, name: '', text: '', links: [], media: [], from: 'net' };
  }
  return out;
}
