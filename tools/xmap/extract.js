// xmap in-page extractor. Evaluates to a JSON-serialisable snapshot of the X page currently rendered.
// Driver-agnostic: runs under Playwright (page.evaluate(source)) or any browser tool that executes page script.
// It only reads the DOM. Anchors are semantic (article, status permalinks, roles, aria-labels, lang/dir, <time>),
// never CSS class names, because X ships hashed/utility classes that change between deploys.
//
// X renders a quoted post two ways, and both are read by the same rule:
//   signed-out: a [role=link] frame (data-href) wrapping a nested <article> that has its own permalink;
//   signed-in:  a [role=link] card holding its own <time>, author and text, with no permalink at all.
// So a quote card is "a non-anchor [role=link] element that holds an <article> or a <time>". Everything inside
// it belongs to the quoted post, never to the post that quotes it. Signed-in, a quoted post X will not show is a
// bare nested <article> holding only a notice ("This post is unavailable.").
(() => {
  const EXTRACTOR_VERSION = '1.1.0';
  const STATUS = /^\/([A-Za-z0-9_]{1,15})\/status\/(\d+)$/;
  const clean = s => (s || '').replace(/ /g, ' ').trim();
  const path = a => { try { return new URL(a.getAttribute('href'), location.origin).pathname; } catch { return ''; } };
  // X's own policy chrome (parody/commentary labels, "Learn more" on withheld posts) is never the author's link.
  const UI_LINK = /^https?:\/\/help\.(x|twitter)\.com\//;
  const isCard = e => e.tagName !== 'A' && !!e.querySelector('article, time');
  const outermost = els => els.filter(e => !els.some(o => o !== e && o.contains(e)));
  // An anchor that displays a URL (as opposed to a mention, cashtag or hashtag link).
  const urlLike = a => /^https?:\/\/t\.co\//.test(a.getAttribute('href') || '') || /^https?:\/\//.test(clean(a.textContent));

  const sanitise = el => {
    const c = el.cloneNode(true);
    c.querySelectorAll('svg,style,script').forEach(n => n.remove());
    c.querySelectorAll('*').forEach(n => { n.removeAttribute('class'); n.removeAttribute('style'); n.removeAttribute('srcset'); });
    return c.outerHTML.slice(0, 30000);
  };

  // Post text with each displayed URL replaced by its target: the expanded URL X puts in the anchor's title
  // (signed-out), else the absolute x.com URL for in-site links, else the t.co href (signed-in shows only a
  // clipped display form; normalize expands t.co from the page's own API responses where it has them).
  const textOf = block => {
    if (!block) return '';
    const c = block.cloneNode(true);
    c.querySelectorAll('img[alt]').forEach(i => i.replaceWith(document.createTextNode(i.getAttribute('alt'))));
    c.querySelectorAll('a').forEach(a => {
      const title = a.getAttribute('title') || '', href = a.getAttribute('href') || '';
      if (/^https?:\/\//.test(title)) a.replaceWith(document.createTextNode(title));
      else if (urlLike(a)) a.replaceWith(document.createTextNode(href.startsWith('/') ? 'https://x.com' + href : href));
    });
    return clean(c.textContent);
  };
  const handlesIn = el => el ? [...new Set([...clean(el.textContent).matchAll(/@([A-Za-z0-9_]{1,15})/g)].map(m => m[1]))] : [];
  // The innermost element whose text starts with "Replying to" (ancestors can start with the same words).
  const replyingIn = els => els.filter(e => /^Replying to\b/.test(clean(e.textContent)) && clean(e.textContent).length < 300)
    .sort((a, b) => clean(a.textContent).length - clean(b.textContent).length)[0] || null;
  const mediaIn = els => [
    ...els.filter(e => e.matches('img[src*="twimg.com/media"],img[src*="tweet_video_thumb"],img[src*="amplify_video_thumb"]')).map(i => ({ type: 'photo', url: i.src, alt: i.alt || '' })),
    ...els.filter(e => e.matches('video')).map(v => ({ type: 'video', poster: v.getAttribute('poster') || '' })),
  ];
  const linkOf = (a, block) => ({
    url: /^http/.test(a.getAttribute('title') || '') ? a.getAttribute('title') : a.href,
    via: a.href, text: clean(a.textContent).slice(0, 300), in_text: !!(block && block.contains(a)),
  });
  // Links of a scope: external anchors and URL-like in-text anchors, minus X's chrome and minus anchors inside
  // a nested [role=link] block (community notes, nested quote previews) that is not the scope itself.
  const linksIn = (anchors, block, scope) => anchors
    .filter(a => !UI_LINK.test(a.href) && (a.getAttribute('target') === '_blank' || (block && block.contains(a) && urlLike(a))))
    .filter(a => { const r = a.parentElement && a.parentElement.closest('[role="link"]'); return !r || r === scope || !scope.contains(r); })
    .map(a => linkOf(a, block));

  // A signed-in quote card (no nested article): author, time, text, media and links read from the card itself.
  const parseCard = card => {
    const nestedArticle = card.querySelector('article');
    const inner = outermost([...card.querySelectorAll('[role="link"]')].filter(isCard));
    const mine = sel => [...card.querySelectorAll(sel)].filter(e => !inner.some(c => c.contains(e)));
    const media = mediaIn(mine('img,video'));
    if (nestedArticle) {
      const base = parsePost(nestedArticle);
      if (base) return { ...base, media: base.media.length ? base.media : media };
    }
    const perma = mine('a[href*="/status/"]').find(a => STATUS.test(path(a)));
    const ref = card.getAttribute('data-href') || (perma ? path(perma) : null);
    const [, refHandle, refId] = (ref && ref.match(STATUS)) || [];
    const at = mine('span').map(s => clean(s.textContent).match(/^@([A-Za-z0-9_]{1,15})$/)).find(Boolean);
    const block = mine('div[dir][lang]')[0] || null;
    const insideCard = (e, sel) => { const m = e.closest(sel); return !!m && card.contains(m); };
    // Author name: the first labelled-direction element that is not post text, the date, the @handle or "·".
    const nameEl = mine('[dir]').find(e => !insideCard(e, '[lang]') && !insideCard(e, '[aria-label]') && !e.querySelector('time') && /^[^@·]/.test(textOf(e)));
    const time = mine('time')[0];
    const handle = refHandle || (at && at[1]) || null;
    if (!handle && !block) return nestedArticle ? { unavailable: true, text: clean(nestedArticle.textContent).slice(0, 300) } : { ref };
    return {
      id: refId || null, handle, name: nameEl ? textOf(nameEl) : '',
      created_at: time ? time.getAttribute('datetime') : null,
      lang: block ? block.getAttribute('lang') : null, text: textOf(block),
      truncated: mine('a,button,span').some(e => /^Show more$/i.test(clean(e.textContent))),
      links: linksIn(mine('a'), block, card), media,
      replying_to: handlesIn(replyingIn(mine('div,span'))),
      quoted: inner.length ? parseCard(inner[0]) : null,
    };
  };

  const parsePost = root => {
    const inRoot = e => e.closest('article') === root;
    const cards = outermost([...root.querySelectorAll('[role="link"]')].filter(e => inRoot(e) && isCard(e)));
    const inCard = e => cards.some(c => c.contains(e));
    // "own": elements that belong to this post, not to a quoted post (card or nested article).
    const own = sel => [...root.querySelectorAll(sel)].filter(e => inRoot(e) && !inCard(e));
    const perma = own('a[href*="/status/"]').find(a => STATUS.test(path(a)));
    if (!perma) return null;
    const [, handle, id] = path(perma).match(STATUS);
    const authorLink = own('a[href="/' + handle + '"]')[0];
    const nameEl = own('a[href="/' + handle + '"] [dir]').find(e => textOf(e) && !/^@/.test(textOf(e)));
    const block = own('div[dir][lang]')[0] || null;
    const group = own('[role="group"][aria-label]').find(g => /repl|repost|like|view/i.test(g.getAttribute('aria-label')));
    // Social context ("Pinned", "<name> reposted") is whatever the article shows before the author's avatar link.
    let context = '';
    if (authorLink) { const r = document.createRange(); r.setStart(root, 0); r.setEndBefore(authorLink); context = clean(r.toString()).slice(0, 200); }
    const bare = [...root.querySelectorAll('article')].filter(a => a.parentElement.closest('article') === root && !inCard(a));
    let quoted = null;
    if (cards.length) quoted = parseCard(cards[0]);
    else if (bare.length) quoted = parsePost(bare[0]) || { unavailable: true, text: clean(bare[0].textContent).slice(0, 300) };
    return {
      id, handle,
      name: nameEl ? textOf(nameEl) : '',
      verified: own('[aria-label="Verified account"]').length > 0,
      date_display: clean(perma.textContent),
      lang: block ? block.getAttribute('lang') : null,
      text: textOf(block),
      truncated: own('a,button,span').some(e => /^Show more$/i.test(clean(e.textContent))),
      links: linksIn(own('a'), block, root),
      media: mediaIn(own('img,video')),
      metrics_label: group ? group.getAttribute('aria-label') : '',
      context,
      replying_to: handlesIn(replyingIn(own('div,span'))),
      quoted,
    };
  };

  const parseProfile = () => {
    const h1 = document.querySelector('h1[dir="auto"]');
    const joined = [...document.querySelectorAll('a[href$="/about"]')].find(a => /^Joined\b/.test(clean(a.textContent)));
    if (!h1 || !joined) return null;
    const handle = path(joined).split('/')[1];
    let hdr = joined; while (hdr && !hdr.contains(h1)) hdr = hdr.parentElement;
    if (!hdr) return null;
    const count = sel => { const a = hdr.querySelector(sel); return a ? clean((a.querySelector('span') || a).textContent) : null; };
    const banner = document.querySelector('img[alt$="profile banner"]');
    const avatar = document.querySelector('a[href$="/photo"] img');
    const meta = joined.parentElement && joined.parentElement.parentElement;
    const items = meta ? [...meta.children] : [];
    const site = items.map(d => d.querySelector('a[target="_blank"]')).find(Boolean);
    const loc = items.find(d => !d.querySelector('a'));
    const bio = [...hdr.querySelectorAll('div[dir="auto"]')].find(d => !d.contains(h1) && !d.closest('a') && !d.closest('h1'));
    const postsCount = [...document.querySelectorAll('div,span')].find(e => !e.children.length && /^[\d.,]+[KMB]? posts$/i.test(clean(e.textContent)));
    const uid = banner && (banner.src.match(/profile_banners\/(\d+)\//) || [])[1];
    return {
      handle, name: clean(h1.textContent), user_id: uid || null,
      verified: !!hdr.querySelector('[aria-label="Verified account"]'),
      bio: textOf(bio), location: loc ? clean(loc.textContent) : '',
      website: site ? { text: clean(site.textContent), via: site.href, url: /^http/.test(site.getAttribute('title') || '') ? site.getAttribute('title') : null } : null,
      joined: clean(joined.textContent),
      following: count('a[href$="/following"]'),
      followers: count('a[href$="/verified_followers"]') || count('a[href$="/followers"]'),
      posts_count: postsCount ? clean(postsCount.textContent) : null,
      avatar: avatar ? avatar.src : null, banner: banner ? banner.src : null,
      // Kept so a later parser fix can re-read the header, as normalize does for posts.
      raw_html: sanitise(hdr),
    };
  };

  const body = clean(document.body ? document.body.innerText : '').slice(0, 20000);
  const signals = {
    login_flow: /^\/(i\/flow\/login|login|account\/access)/.test(location.pathname),
    challenge: /(unusual activity|verify (you are|you're) human|confirm (it's|it is) you|arkose|captcha)/i.test(body),
    rate_limited: /(rate limit|try again later|you are over the daily limit)/i.test(body),
    error: /(something went wrong|this account doesn.t exist|account suspended|these posts are protected)/i.test(body),
    signin_wall: /(sign in to x|sign up for x|log in to see|see .{1,60}s full profile)/i.test(body),
  };

  const tops = [...document.querySelectorAll('article')].filter(a => !a.parentElement.closest('article'));
  const posts = [];
  for (const a of tops) { const p = parsePost(a); if (p) { p.raw_html = sanitise(a); posts.push(p); } }
  return {
    extractor_version: EXTRACTOR_VERSION, url: location.href, title: document.title,
    scroll: { y: Math.round(scrollY), height: document.documentElement.scrollHeight },
    signals, profile: parseProfile(), posts, article_count: tops.length,
  };
})()
