# X-map

Maps specific X accounts, one at a time, into versioned files: an exact dataset of what each account posted
and a cited dossier (`map.md`) of what it argues, predicts, amplifies and links to. It replaces reading an
account and copying it by hand. It drives one signed-in browser session at reading pace; it does not use the
X API.

```
accounts/<handle>/
  account.json    capture window and focus for this account
  raw/<run_id>/   immutable evidence of each browser run (run.json, articles.jsonl.gz, net/)
  posts.jsonl     one post per line, newest first, exact UTC timestamps, exact engagement counts
  profile.json    latest profile snapshot
  stats.json      deterministic aggregates (cadence, network, domains, cashtags, top posts)
  map.md          the dossier; every statement cites [p:<post id>]
```

| Command | Does |
|---|---|
| `bin/xmap run <handle>` | capture, normalize, stats, validate the data |
| `bin/xmap validate <handle> --require-map` | acceptance gate; ends with `pending=<n>` |
| `npm test` | extractor and pipeline tests against real X markup |

- Sign-in for cloud sessions: [docs/SETUP.md](docs/SETUP.md).
- Contracts and conduct every agent follows: [CLAUDE.md](CLAUDE.md).
- Launch prompt for a mapping run: [prompts/lead.md](prompts/lead.md); workers: [.claude/agents/](.claude/agents/).

Add an account by asking a session to map `@handle`, or by copying `accounts/astridwilde/account.json`.
