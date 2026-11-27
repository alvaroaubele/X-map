# X-map

Maps specific X accounts, one at a time, into versioned files: an exact dataset of what each account posted
and a cited dossier (`map.md`) of what it argues, predicts, amplifies and links to. It replaces reading an
account and copying it by hand. It drives one signed-in browser session at reading pace; it does not use the
X API.

```
accounts/<handle>/
  account.json    the operator's review-gate answers: window, surfaces, focus, relevance rule
  raw/<run_id>/   immutable evidence of each browser run (run.json, articles.jsonl.gz, net/)
  posts.jsonl     one post per line, newest first, exact UTC timestamps, exact engagement counts
  profile.json    latest profile snapshot
  stats.json      deterministic aggregates (cadence, network, domains, cashtags, top posts)
  map.md          the dossier; every statement cites [p:<post id>]
```

| Command | Does |
|---|---|
| `bin/xmap start <handle>` then `bin/xmap status` | capture detached (long windows), then normalize, stats, validate |
| `bin/xmap budget` | posts the session read in the last 24 hours against the daily budget |
| `bin/xmap validate <handle> --require-map` | acceptance gate; ends with `pending=<n>` |
| `npm test` | extractor and pipeline tests against real X markup |

- Sign-in for cloud sessions: [docs/SETUP.md](docs/SETUP.md).
- Contracts and conduct every agent follows: [CLAUDE.md](CLAUDE.md).
- Launch prompt for a mapping run: [prompts/lead.md](prompts/lead.md); workers: [.claude/agents/](.claude/agents/).

Add an account by asking a session to map `@handle` with [prompts/lead.md](prompts/lead.md): it asks the review-gate
questions once and writes `accounts/<handle>/account.json` from `tools/xmap/account.template.json`.
New-account procedure and planning numbers: [docs/PLAYBOOK.md](docs/PLAYBOOK.md). Lessons from past runs, with
evidence: [docs/LESSONS.md](docs/LESSONS.md).
