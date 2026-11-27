// Re-run the current extractor over the sanitised article HTML a raw run stored for each post.
// This is how a parsing fix reaches posts that were captured before it: raw runs stay untouched, and normalize
// re-derives their fields in memory. Offline: a headless browser renders the stored HTML at an x.com URL that is
// fulfilled locally (so relative links resolve as on X) and every other request is aborted.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
export const EXTRACTOR_SRC = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '../extract.js'), 'utf8');
export const EXTRACTOR_VERSION = (EXTRACTOR_SRC.match(/EXTRACTOR_VERSION = '([^']+)'/) || [])[1];
const PAGE = 'https://x.com/__xmap_reparse__';

// A row needs re-parsing when it was extracted by another extractor version and still carries its article HTML.
export const isStale = r => !!(r.raw_html && r.extractor_version && r.extractor_version !== EXTRACTOR_VERSION);

// Rows captured from live pages keep what sanitising removed (inline SVG carries the verified badge) and what
// capture itself supplied (a permalink row's timeline context).
function merge(row, fresh) {
  const { raw_html, ...f } = fresh;
  const out = { ...row, ...f, verified: !!(row.verified || f.verified), extractor_version: EXTRACTOR_VERSION, reparsed_from: row.extractor_version };
  if (row.surface === 'permalink') { out.context = row.context; if (!out.replying_to.length) out.replying_to = row.replying_to || []; }
  return out;
}

export async function reparse(rows) {
  if (!rows.length) return [];
  let chromium;
  try { ({ chromium } = require('playwright')); } catch {
    throw new Error(`reparse: ${rows.length} posts were extracted by an older extractor and need playwright to be re-read from raw_html`);
  }
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const html = '<!doctype html><html><head><meta charset="utf-8"></head><body><main>' + rows.map(r => `<div>${r.raw_html}</div>`).join('\n') + '</main></body></html>';
    await page.route('**/*', r => (r.request().url() === PAGE ? r.fulfill({ contentType: 'text/html; charset=utf-8', body: html }) : r.abort()));
    await page.goto(PAGE);
    const snap = await page.evaluate(EXTRACTOR_SRC);
    if (snap.posts.length !== rows.length || snap.posts.some((p, i) => p.id !== rows[i].id)) {
      throw new Error(`reparse: stored HTML yielded ${snap.posts.length} posts for ${rows.length} rows; the extractor no longer recognises some captured articles`);
    }
    return rows.map((r, i) => merge(r, snap.posts[i]));
  } finally { await browser.close(); }
}
