# X-map run lessons

Lessons from real runs, each with the evidence behind it and the prompt or tool change it calls for. Read this
before changing `prompts/lead.md`, `.claude/agents/*.md` or `tools/xmap/`. Add new runs at the top.

## Run 1 follow-ups: ledger, backtest and playbook, 2026-11-27

[PLAYBOOK.md](PLAYBOOK.md) now turns sections A–G into the ordered procedure for a new account, with run 1's
planning numbers. Points not recorded above:

| # | Lesson | Evidence | Status |
|---|---|---|---|
| H1 | Capture speed is steady at ~48 posts/min, ~2.9 posts per scroll step, so runtime and reads can be estimated before a run: an hour is ~2,900 reads. | `run.json` of `101916Z` (508 in 10.6 min) and `122804Z` (3,183 in 65.7 min, 1,101 steps) | Note, in PLAYBOOK §2 |
| H2 | The budget counts a run from its start time, so capacity returns run by run, 24 h after each run started, not all at once. | `lib/budget.mjs` `runTime(run_id)` | Note |
| H3 | Two thirds of posts needed a per-post triage judgment (2,103 overrides for 3,183 posts); the first-pass rules decided the rest. Triage is mapper work to budget for, not a filter that runs by itself. | `triage_overrides.jsonl` | Note |
| H4 | The signed-in profile header reads wrong from the page (name "…’s posts", bio "Click to Unfollow …"), as stored in `run.json`. `profile.json` is built from the `UserByScreenName` response (`source: api`) and is correct. | `run.json` of `101916Z`..`122804Z` vs `profile.json` | Fixed for `profile.json`; `run.json.profile` still holds the page reading |
| H5 | Analyses built on the posts (trade ledger, price backtest) live under `accounts/<handle>/<analysis>/` with a deterministic build script, stored external data and their own `verify.py`; `validate` does not cover them. | PR #6, `accounts/astridwilde/backtest/` | Pattern, in PLAYBOOK §9 |
| H6 | The `reposts` surface opens `x.com/<handle>/reposts`. Whether X serves a reposts timeline at that URL is unverified; it has never run. | `capture.mjs` `SURFACE_URL` | Open: check on first use |

## Setup changes after run 1, 2026-11-27

Sections A–F below proposed these; each row's Status column now says where it landed. Three further points
came out of implementing them:

| # | Lesson | Status |
|---|---|---|
| G1 | `run.latest_ok` passed any run whose status was `ok`, including ones that stopped on `max_posts`, `max_minutes` or a mislabelled `end_of_timeline`. It now passes on how each surface stopped, or on proof the window was served. | Fixed, with a test |
| G2 | The rate limit belongs to the operator's session, not to the account being mapped, so the read budget is one number for the repository, not one per account as F2 proposed. | Fixed |
| G3 | A cloud session picks up an environment variable when it resumes, not only when it starts: the session that could not see `X_AUTH_TOKEN` at 10:00 had it at 16:00. A logged-out test must unset it. | Note |

Still open: the DependencyError recovery (A5) has not met a live error; `replies` and `reposts` have not run
signed-in; nothing resumes a window without re-reading it from the top.

## Run 1: @astridwilde, 2026-11-27

Six capture runs: 6,803 posts read in total, ending with 3,183 unique posts covering 2023-07-14 to 2026-11-27.
Three verifier rounds raised 16, 14 and 13 findings. Merged in PRs #1–#3.

### A. Capture

| # | Lesson | Evidence | Status |
|---|---|---|---|
| A1 | A passive network recorder must allowlist what it stores. Recording every x.com GraphQL response stored the operator's Grok account JWT, their home timeline, sidebar recommendations, trends and pinned lists. | run `20261127T101916Z`, 12 files, deleted | Fixed: `NET_KEEP` in `lib/util.mjs` |
| A2 | Signed-in markup is not the signed-out markup. A quoted post is a card with no nested `article` and no permalink, so extractor 1.0.0 read all 508 posts as plain posts. Validate passed anyway. | first signed-in run | Fixed in extractor 1.1.0, with a fixture |
| A3 | The metrics aria-label includes the viewer's own state ("Liked", "Reposted", "Bookmarked"). It was parsed as 0 likes on 44 posts. | `parseMetrics` | Fixed |
| A4 | The signed-in profile serves `UserOriginalsTimeline`, which leaves out reposts and replies to others. Amplification is then visible only through quotes. | every signed-in run | Gate question 2 in `prompts/lead.md`; `reposts` surface added to capture. `replies` and `reposts` have not yet run signed-in. |
| A5 | Deep timeline pages fail intermittently with `DependencyError` while a continuation cursor still exists. The stall detector reported this as `end_of_timeline`. The error moved between runs (2026-08-07, then 2024-12-09), so it is not a depth limit. | `net/0036` of `111242Z`; `113414Z` | Fixed: `server_error` stop, plus Retry / Try again or scroll-back recovery (max 3). Not yet exercised live. |
| A6 | Every run restarts from the top of the profile, so each retry or window expansion re-reads everything already captured. X rate-limited the session after about 6,800 post reads in one day. | `122804Z` `blocked:rate_limited` | Fixed: `lib/budget.mjs` counts signed-in reads of the last 24 hours across accounts (6,798 for this run); capture stops at the remaining budget and refuses to start at zero. Budget 6,000 per day in `xmap.json`, set from this one observation. Open: resuming a window without re-reading from the top. |
| A7 | The harness kills background commands after 2 hours, short of a 300-minute capture budget. Detach long captures (`setsid nohup … &`) and poll the log. | run `111218Z` killed (status error, 0 posts) | Fixed: `bin/xmap start` detaches the capture in its own session, `bin/xmap status` reports it and its exit code; one capture at a time is enforced. |
| A8 | Extractor fixes must reach old runs. `normalize` now re-reads the stored `raw_html` offline (`lib/reparse.mjs`), and the page's own API responses fill gaps the DOM lacks: quoted ids, `t.co` targets, self-thread replies (`lib/net.mjs`). | 513 rows reparsed | Fixed |

### B. Validation gaps

| # | Lesson | Status |
|---|---|---|
| B1 | Validate proved internal consistency, not correctness. It passed misread data (A2). Add a cross-check between the DOM and the stored API responses, for example the count of quotes in `posts.jsonl` against the count of `quoted_status_result` entries in the same run's timeline responses. | Fixed: `xcheck.timeline_ids_captured` and `xcheck.quotes_agree`, compared per post id; a test reproduces A2 and fails the check. |
| B2 | `map.quotes_verbatim` checks blockquote lines only. Inline quoted fragments in tables and prose went unchecked; the mapper and verifier caught paraphrases inside quotation marks by hand. Extend the check to every `"…"` fragment on a line that carries `[p:id]`. | Fixed: `map.inline_quotes_verbatim` (283 fragments in this map; the one failure was a cross-reference in quotation marks, now italics per the map contract). |
| B3 | `run.latest_ok` was strictly "status is ok", so a run that was blocked after covering the window failed forever. It now passes only when the run's own timeline responses show posts older than `since`; changing `since` to 2022-01-01 makes the same run fail. | Fixed |
| B4 | Triage needs its own checks: `triage.current` (matches `posts.jsonl`, nothing unjudged) and `map.citations_kept`. | Fixed |

### C. Relevance triage

| # | Lesson | Status |
|---|---|---|
| C1 | The operator's relevance rule arrived mid-run and changed twice: first "skip filler", then "keep one-word endorsements of substantive quoted posts". Each change cost a full re-triage, a re-map and a verifier round. Ask for this rule at the review gate. | Fixed: `<review_gate>` in `prompts/lead.md`; answers live in `account.json`; signed-in capture refuses to start without `gate.confirmed`. |
| C2 | Phrase lists do not find endorsements. "enthusiastically cosigned", "cry harder" and "trends that will continue" slipped through. The structural rule works: a quote with 6 or fewer own words, of a post with text, goes to review and is never auto-skipped. | Fixed in `triage.mjs` |
| C3 | Triage judgments must live in the repo (`triage_overrides.jsonl`), and `bin/xmap triage` must rebuild `triage.jsonl` byte-identical. Scratchpad scripts are lost. | Fixed |

### D. Map quality (what the verifier kept catching)

Every round found real semantic errors that the mapper's self-checks missed. Give the mapper these rules up
front:

1. Date a claim from the post id that states it. A quoted or re-quoted post has its own date, sometimes from
   before the window (the ad-platform thesis is 2022-12-09, not 2023-07-28).
2. Attribute quoted claims to the quoted author. An endorsement is the account's stance, not its claim
   (AntonHand's prediction, BrendanFoody's "100X").
3. A reversal needs both posts and the same subject. "LLM skeptic, then convert" was really a synthetic-data
   reversal.
4. Holdings come from a disclosed book or an explicit trade, not from advice. "Easier to own the software basket"
   is not a position.
5. Counts and rankings come from a command, re-run after every triage change. "541 accounts" went stale.
6. Coverage must describe the validator's current output, not what it printed earlier.
7. Words like "steady", "main device" or "most-argued" are interpretation. Label them or back them with a count.

### E. Orchestration and efficiency

| # | Lesson |
|---|---|
| E1 | Resuming the same account-mapper across rounds kept its context and saved re-reading. Each verifier must be fresh, so its judgment stays independent. |
| E2 | Mapper rounds cost 250k–700k tokens each, and five rounds ran. Most of that was rework from C1 (rule changes) and D (errors the verifier caught). Fix C1 and D in the prompts first; they cut cost the most. |
| E3 | Commit each raw run as soon as it is complete. A container loss would otherwise destroy hours of capture. The account commit (dataset, triage, map) still comes once, after the verifier. |
| E4 | The repo had no `main` branch. The operator wants every PR merged into `main` (now in CLAUDE.md). |
| E5 | Have the verifier dump the cited posts it reads to the scratchpad and pass the path to the mapper. It cuts the mapper's lookup work. |

### F. Changes proposed to `prompts/lead.md` (made in the follow-up below)

1. **Review gate before the first capture**, answered once by the operator, with the answers written to
   `account.json`:
   - the final window (`since`)
   - the surfaces
   - the relevance rule, including how endorsements and one-word quotes are treated
   - what amplification the operator needs; reposts are absent signed-in, so say so here
2. **Read budget:** about 6,500 posts per account per session at most. One full-window run first, never a shallow
   run followed by a deeper one.
3. **Long captures:** run detached and poll the log. Never as a harness background task.
4. **account-mapper:** add the rules in section D.
5. **map-verifier:** add a mandatory pass that samples skipped and kept triage posts, and one that checks every
   inline quote.
6. **Finish line:** validate `pending=0` and the verifier resolved, then the account commit, the PR and the merge
   into `main`.
