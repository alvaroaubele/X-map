// xmap in-page extractor. Evaluates to a JSON-serialisable snapshot of the X page currently rendered.
// Driver-agnostic: runs under Playwright (page.evaluate(source)) or any browser tool that executes page script.
// It only reads the DOM. Anchors are semantic (article, status permalinks, aria-labels, lang/dir attributes),
// never CSS class names, because X ships hashed/utility classes that change between deploys.
(() => {
  const EXTRACTOR_VERSION = '1.0.0';
  const STATUS = /^\/([A-Za-z0-9_]{1,15})\/status\/(\d+)$/;
  const clean = s => (s || '').replace(/ /g, ' ').trim();
  const path = a => { try { return new URL(a.getAttribute('href'), location.origin).pathname; } catch { return ''; } };

  const sanitise = el => {
    const c = el.cloneNode(true);
    c.querySelectorAll('svg,style,script').forEach(n => n.remove());
    c.querySelectorAll('*').forEach(n => { n.removeAttribute('class'); n.removeAttribute('style'); n.removeAttribute('srcset'); });
    return c.outerHTML.slice(0, 30000);
  };

  // Post text with t.co links replaced by the expanded URL X puts in the anchor's title attribute.
  const textOf = block => {
    if (!block) return '';
    const c = block.cloneNode(true);
    c.querySelectorAll('img[alt]').forEach(i => i.replaceWith(document.createTextNode(i.getAttribute('alt'))));
    c.querySelectorAll('a[title^="http"]').forEach(a => a.replaceWith(document.createTextNode(a.getAttribute('title'))));
    return clean(c.textContent);
  };

  const parsePost = root => {
    // "own": elements that belong to this article and not to a nested (quoted) article.
    const own = sel => [...root.querySelectorAll(sel)].filter(e => e.closest('article') === root);
    const perma = own('a[href*="/status/"]').find(a => STATUS.test(path(a)));
    if (!perma) return null;
    const [, handle, id] = path(perma).match(STATUS);
    const nameEl = own('a[href="/' + handle + '"] [dir="auto"]')[0];
    const block = own('div[dir="auto"][lang]')[0] || null;
    const group = own('[role="group"][aria-label]').find(g => /repl|repost|like|view/i.test(g.getAttribute('aria-label')));
    const first = root.firstElementChild;
    const context = first && !first.querySelector('[data-post-avatar]') && !first.contains(perma) ? clean(first.textContent) : '';
    const replying = own('div,span').find(e => /^Replying to\b/.test(clean(e.textContent)) && clean(e.textContent).length < 300);
    const frame = own('[data-slot="embedded-tweet-frame"]')[0];
    const nested = frame ? frame.querySelector('article') : null;
    const inBlock = e => block && block.contains(e);
    return {
      id, handle,
      name: nameEl ? clean(nameEl.textContent) : '',
      verified: own('[aria-label="Verified account"]').length > 0,
      date_display: clean(perma.textContent),
      lang: block ? block.getAttribute('lang') : null,
      text: textOf(block),
      truncated: own('a,button,span').some(e => /^Show more$/i.test(clean(e.textContent))),
      links: own('a[target="_blank"]').map(a => ({
        url: /^http/.test(a.getAttribute('title') || '') ? a.getAttribute('title') : a.href,
        via: a.href, text: clean(a.textContent).slice(0, 300), in_text: !!inBlock(a),
      })),
      media: [
        ...own('img[src*="twimg.com/media"],img[src*="tweet_video_thumb"],img[src*="amplify_video_thumb"]').map(i => ({ type: 'photo', url: i.src, alt: i.alt || '' })),
        ...own('video').map(v => ({ type: 'video', poster: v.getAttribute('poster') || '' })),
      ],
      metrics_label: group ? group.getAttribute('aria-label') : '',
      context,
      replying_to: replying ? [...replying.querySelectorAll('a')].map(a => path(a).slice(1)).filter(Boolean) : [],
      quoted: nested ? parsePost(nested) || { ref: frame.getAttribute('data-href') } : (frame ? { ref: frame.getAttribute('data-href') } : null),
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
