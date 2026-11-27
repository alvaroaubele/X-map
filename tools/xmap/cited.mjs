#!/usr/bin/env node
// xmap cited: every post map.md cites, in the order the map cites it, with what the post itself says and when.
//   node tools/xmap/cited.mjs <handle> [--section "Theses and claims"]
// Each entry shows the map line(s) carrying the citation, then the post's date (from its id), kind, author, own text,
// and the quoted post with ITS author and date. This is the lookup a mapper or verifier would otherwise do by hand.
import fs from 'node:fs';
import path from 'node:path';
import { accountDir, readJsonl, parseArgs } from './lib/util.mjs';

const one = s => (s || '').replace(/\s+/g, ' ').trim();
export function cited(handle, section) {
  const dir = accountDir(handle);
  const byId = new Map(readJsonl(path.join(dir, 'posts.jsonl')).map(p => [p.id, p]));
  const md = fs.readFileSync(path.join(dir, 'map.md'), 'utf8');
  const out = new Map(); let head = '';
  md.split('\n').forEach((line, i) => {
    const h = line.match(/^## (.+)$/); if (h) head = h[1].trim();
    if (section && head !== section) return;
    for (const m of line.matchAll(/\[p:(\d+)\]/g)) {
      if (!out.has(m[1])) out.set(m[1], { id: m[1], post: byId.get(m[1]) || null, lines: [] });
      out.get(m[1]).lines.push({ n: i + 1, section: head, text: line });
    }
  });
  return [...out.values()];
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = parseArgs(process.argv.slice(2));
  if (!a._[0]) { console.error('usage: cited.mjs <handle> [--section "<map section>"]'); process.exit(2); }
  const rows = cited(a._[0].replace(/^@/, ''), a.section);
  for (const r of rows) {
    const p = r.post;
    console.log(`\n[p:${r.id}] ${p ? `${p.created_at ? p.created_at.slice(0, 10) : 'undated'} ${p.kind} by @${p.author}` : 'NOT IN posts.jsonl'}`);
    if (p) {
      console.log(`  own:    ${one(p.text) || '(no text)'}`);
      if (p.quoted) console.log(`  quotes: @${p.quoted.handle || '?'} ${p.quoted.created_at ? p.quoted.created_at.slice(0, 10) : 'undated'}: ${one(p.quoted.text) || '(no text)'}`);
      if ((p.replying_to || []).length) console.log(`  reply to: ${p.replying_to.map(h => '@' + h).join(' ')}`);
    }
    for (const l of r.lines) console.log(`  map ${l.n} (${l.section}): ${one(l.text).slice(0, 260)}`);
  }
  console.log(`\ncited_posts=${rows.length}`);
}
