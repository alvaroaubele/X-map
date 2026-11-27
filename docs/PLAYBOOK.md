# New-account playbook

How to take one new handle from nothing to a merged map at the lowest read and token cost, distilled from
run 1 (@astridwilde, 2026-11-27). This file is the procedure; [LESSONS.md](LESSONS.md) holds the evidence
behind each step (cited by its id, e.g. A6) and [prompts/lead.md](../prompts/lead.md) is the launch prompt
that executes it. When a run changes a step, update this file and add the evidence to LESSONS.md.

## 1. What run 1 cost, and what it should have cost

| | Run 1 actual | With this playbook |
|---|---|---|
| Signed-in capture runs | 5 (plus 1 logged-out) | 1 |
| Posts read against the session limit | 6,798 for 3,183 unique posts (2.14 reads per post) | ~3,183 (1.0) |
| Capture outcome | `blocked:rate_limited` on the last run, capturing over for the day | window read within budget |
| Relevance rule | arrived after capture, changed twice | answered at the gate |
| Mapper rounds | 5, at 250k–700k tokens each (E2) | fewer: most rework came from the rule changes (C1) and the map errors in D |
| Verifier rounds / findings | 3 / 16, 14, 13 | target: one round to `no findings` |

The overspend had three causes, each now closed by a step below: a shallow window widened twice (each
widening re-reads from the newest post, A6), a run killed by the harness's 2-hour limit (A7), and a
`DependencyError` misread as the end of the timeline (A5).

## 2. Planning numbers (one observation each; refine them as runs accumulate)

| Quantity | Run 1 value | Source |
|---|---|---|
| Session limit | blocked after ~6,800 posts served in one day; budget set to 6,000 | `xmap.json`, run `20261127T122804Z` |
| Budget clock | rolling 24 h, each signed-in run counted from its start time (`run_id`), all accounts together | `tools/xmap/lib/budget.mjs` |
| Read speed | ~48 posts/min (508 in 10.6 min; 3,183 in 65.7 min) | `run.json` `started_at`/`ended_at` |
| Posts per scroll step | ~2.9 (3,183 posts / 1,101 steps) | `run.json` surfaces |
| Own-post density | 3,183 posts in 3.37 years, rising from 338 (2023 H2) to 1,397 (2026) | `stats.json` `by_month` |
| Own posts vs. profile `posts_count` | 943 per year captured vs. 42,007 lifetime over 17.4 years (2,414 per year); the lifetime count includes reposts and replies | `profile.json` |
| Triage keep rate | 1,323 kept of 3,183 (41.6%) | `validate` `triage.current` |
| Per-post triage judgments | 2,103 of 3,183 posts (66%) needed an override; first-pass rules decided the rest | `triage_overrides.jsonl` |

Sizing a window before any read: take the profile's `posts_count` per year of account age as an upper
bound on posts-tab reads per year (run 1: actual was 0.39 of it), weight toward recent years, and compare
with `bin/xmap budget`. Runtime is reads / 48 minutes; anything above ~2,900 reads (an hour) goes through
`bin/xmap start`.

## 3. Before the first read

1. `test -n "$X_AUTH_TOKEN" && echo session-token-present`. Without it, follow [SETUP.md](SETUP.md); a
   logged-out run returns ~5 posts before the sign-in wall (run `20261127T100213Z`) and is not worth a run.
2. `bin/xmap budget`. If `remaining` is below the window's estimate, wait: one full run, never a shallow run
   followed by a deeper one (A6, F2).
3. Review gate (`prompts/lead.md` `<review_gate>`), all four questions in one message, answers written to
   `accounts/<handle>/account.json` in the operator's words with `gate.confirmed` set. Capture refuses to
   start without it. Recommended first answers, from run 1:
   - Window: the final start date now. Widening later re-reads everything.
   - Surfaces: `posts`. Add `replies` or `reposts` only if the amplification answer needs them, and say
     that their first signed-in use is also an extractor test (section 8).
   - Relevance: run 1's rule and endorsement clause (`accounts/astridwilde/account.json`) as the default
     wording: skip posts with no substantive content; keep a short quote that only endorses or rejects a
     quoted post carrying a forecast, claim or position, and attribute the claim to the quoted author.
   - Amplification: state that signed-in `posts` shows amplification through quotes only (A4).

## 4. Capture

1. `bin/xmap start <handle>`, then `bin/xmap status` every few minutes. Never a harness background task:
   the harness kills it at 2 hours (A7).
2. On exit, act on the code before anything else:

| Exit | Meaning | Action |
|---|---|---|
| 0 | finished | commit and push the raw run at once (E3) |
| 1 | `error` (e.g. navigation timeout) | retry once, only if `bin/xmap budget` has room for the whole window |
| 2 + `gate_missing` | gate not answered | back to section 3 |
| 3 / 4 | `auth_failed` / `blocked` | no more captures this session; report `run.json`, continue browser-free work |
| 5 | `read_budget` | wait until the oldest counted run is 24 h old |

3. Commit the raw run, then `bin/xmap normalize`, `stats`, `validate <handle>`.

## 5. Data acceptance

The data is ready for a map only when every `data.*`, `run.*` and `xcheck.*` line is `ok`. Validate once
passed misread data (A2), so `xcheck.*` now compares the page against the API responses of the same run.

| Failing check | Action |
|---|---|
| `run.latest_ok` | report how far the run read; the operator chooses a later full re-read or a window ending where it stopped |
| `xcheck.*` | extractor or capture defect: save a fixture under `tests/fixtures/`, fix `tools/xmap/`, extend `npm test`, `normalize` again. Never edit rows by hand. |
| `account.gate` | gate missing or unconfirmed |

## 6. Triage

1. `bin/xmap triage <handle>` applies the first-pass rules. Short quotes (6 or fewer own words) of a post
   with text always go to review; phrase lists miss endorsements (C2).
2. Every per-post judgment goes into `triage_overrides.jsonl` in the repo, so `triage` rebuilds
   `triage.jsonl` byte-identical (C3). Budget for roughly two thirds of posts needing a judgment.
3. A rule change after triage costs a full re-triage, re-map and verifier round; tell the operator once,
   then do it.

## 7. Map and verify

1. One `account-mapper` per account. Its rules already include LESSONS section D: date claims from the
   stating post (a quoted post keeps its own, possibly pre-window, date); attribute quoted claims to the
   quoted author; a reversal needs both posts on the same subject; holdings only from a disclosed book or
   explicit trade; counts from a command, re-run after every triage change; Coverage from the current
   validate output; interpretive words labelled or counted.
2. A new `map-verifier` for every round, with `seed: <round>`; it samples triage decisions with
   `bin/xmap triage-sample` and checks inline quotes.
3. Send findings to the same mapper by message; it keeps the corpus in context (E1). Have the verifier write
   the cited posts it read to the scratchpad and pass the path (E5).
4. Done when `bin/xmap validate <handle> --require-map` prints `pending=0` and the latest verifier round
   returns `no findings` or every remaining finding has a recorded decision.

## 8. Finish

1. Raw runs: already committed one per run.
2. One account commit: `account.json`, `posts.jsonl`, `profile.json`, `stats.json`, triage files, `map.md`.
3. Push to the session branch, open the PR against `main`, and merge it into `main` once `npm test` and
   validate pass. Standing instruction from the operator: no need to ask before merging.
4. Add what the run taught to LESSONS.md under a new run heading, and update this playbook's steps and
   numbers.

## 9. Optional: derived analyses

Run 1 added a trade ledger and an IBKR price backtest after the map (PR #6,
`accounts/astridwilde/backtest/`). Reuse the pattern for any analysis built on the posts:

- A deterministic script that rebuilds the output from `posts.jsonl` (`build_ledger.py`), and a separate
  check (`verify.py`) that every cited id exists, every date matches the post id, and every quote is
  verbatim. `validate` does not cover these files.
- External data (prices) stored in the repo next to the script, so the output reproduces offline; confirm
  determinism by running twice and comparing hashes.
- State how much is modelled: run 1 had no full book before 2024-09-30 and 11–59% of each book undisclosed,
  and 70 of 92 claimed returns were uncheckable (`backtest.json` `claims_check`).

## 10. Untested paths: check these on first use

| Path | Status after run 1 | First-use check |
|---|---|---|
| `replies` surface signed-in | never run | `xcheck.*` ok and replies present in `posts.jsonl` `kind=reply` with other-account targets |
| `reposts` surface signed-in | never run; capture opens `x.com/<handle>/reposts` | confirm X serves a reposts timeline at that URL before relying on it [verify]; if not, reposts may only appear on the `with_replies` surface |
| `DependencyError` recovery (Retry / scroll-back, max 3) | the one run with the code (`20261127T122804Z`) met no such error | look in the `bin/xmap start` log for `timeline error (DependencyError); waiting, then Retry control 1/3` (or `scroll back`), and for a stop reason other than `server_error` |
| Resume a window without re-reading from the top | not built | none; until it exists, a wider window is a full re-read |
| Budget of 6,000 | set from one block at ~6,800 | lower it in `xmap.json` if a run is blocked below it |
