# min_score calibration for prefetch (phase 1)

Date: 2026-10-12. Read-only against prod AMES (owner hermes-default). No retain/delete was issued.

## Method
- Queries: 130 real user prompts from ~/.hermes/state.db (last 60 days, deduped, system/injected
  messages and prompts under 4 words excluded). Script: calibration/sample.py, calibration/replay.py.
- Each replayed with `{"query", "size": 8}` and no min_score; per-hit fused `score` recorded (1040 hits).
- Hand-labelled sample: calibration/labelled-sample.json (ids, kind, rank, score, label only; prompt and memory text withheld because the repo is public), 45 hits = top-5 of 9 of those prompts
  (13 relevant, 32 irrelevant). Every hit was read before labelling. relevant = would help the agent act on that prompt.
- Not benchmark data.

## Finding: the fused score barely discriminates relevance
- Scores over all 1040 hits span 0.01790-0.01885. The server computes `score = rrf + recency` with
  RANK_CONSTANT 60, so it is mostly a function of rank position (rank 0 median 0.01883, rank 7 median 0.01815).
- On the labelled sample AUC of score as a relevance ranker is 0.65 (0.5 = chance). Mean score relevant 0.01870 vs irrelevant 0.01862.
- A threshold therefore cannot separate relevant from irrelevant; it can only trim the tail.
- The dominant noise is not low-score: 144 of 650 top-5 hits across the 130 queries are `procedural`,
  and they are only 2 distinct docs (project-profile blobs). 0 of 11 labelled procedural hits were relevant.
  Excluding procedural hits drops median injected chars from 8271 to 1580.

## Curve (130 queries, size 5; loss/drop counted on the 45-hit labelled sample)
| min_score | abstain rate (130 q) | median injected chars (size 5) | relevant lost (13) | irrelevant dropped (32) |
|---|---|---|---|---|
| off | 0% | 8271 | - | - |
| 0.0183 | 0% | 8271 | 0 (0%) | 0 (0%) |
| 0.01835 | 0% | 8271 | 0 (0%) | 0 (0%) |
| 0.0184 | 0% | 7927 | 0 (0%) | 2 (6%) |
| 0.01845 | 0% | 7687 | 1 (8%) | 5 (16%) |
| 0.0185 | 0% | 7637 | 1 (8%) | 5 (16%) |
| 0.0186 | 0% | 6823 | 5 (38%) | 14 (44%) |
| 0.0187 | 8% | 288 | 6 (46%) | 26 (81%) |
| 0.0188 | 30% | 149 | 8 (62%) | 29 (91%) |
| 0.0189 | 100% | 0 | 13 (100%) | 32 (100%) |

## Chosen threshold: 0.0184
Rule from the card: drop the most irrelevant hits while losing <=5% of relevant ones. 0.0184 is the highest
tested value with 0/13 relevant lost (0.01845 already loses 1/13 = 8%). It drops 2/32 irrelevant hits and
trims median injected chars 8271 -> 7927 (-4%). Abstain rate on real prompts: 0%.

This is a safety floor, not a fix for context bloat. The floor removes only the bottom-ranked tail. The
sample is small (13 relevant); the 5% budget cannot be resolved at this size, so the choice is conservative.
Override with AMES_PREFETCH_MIN_SCORE (empty/off disables).

## Implication for the next step
Context bloat (median 15.8k chars at size 8, 8.3k at size 5) comes from per-kind noise and result size, not from low scores.
Candidate levers, not done here: exclude/limit `procedural` in prefetch, a relevance signal beyond RRF (the server's
cross-encoder `rerank_score`, off by default), smaller size. Tag filtering stays blocked on retain-time tagging (phase 2).

## Config precedence
`AMES_PREFETCH_MIN_SCORE` env > `prefetch_min_score` in `<HERMES_HOME>/agent_memory_es/config.json` (the
value the desktop panel saves) > built-in default 0.0184. `""`/`off`/`none`/`false` disables; an unparseable
value falls back to the default.

## Verification transcripts (python3.12, read-only against prod recall)

Abstain-branch mutation (`self._last = [] if r.get("abstained") else r.get("fused", [])` -> `self._last = r.get("fused", [])`):

    mutant : FAILED tests/test_min_score.py::test_abstained_response_injects_nothing  (1 failed, 14 passed)
    restore: 15 passed in tests/test_min_score.py; full suite 21 passed

Stored-config mutation (drop the `_stored_prefetch_min_score()` read): 2 failed
(`..._read_from_stored_config`, `..._stored_off_disables`), 13 passed; restored -> green.

Session smoke: worktree plugin loaded through Hermes' `load_memory_provider`, driven via
`MemoryManager.prefetch_all` + `build_memory_context_block` (the same path `run_agent` uses), prod recall:

    # 1. default config, real query -> INJECTS
    resolved min_score: 0.0184
    request body (minus query): {"size": 5, "min_score": 0.0184}
    response abstained: False hits: 5
    raw injected chars: 7994 | context block chars: 8218
    recall_status: RecallStatus(provider_label='agent-memory-es', count=5)

    # 2. panel-stored prefetch_min_score=0.0189 (config.json, no env), same query -> ABSTAINS
    resolved min_score: 0.0189
    request body (minus query): {"size": 5, "min_score": 0.0189}
    response abstained: True hits: 0
    raw injected chars: 0 | context block chars: 0
    recall_status: None
    block head: <nothing injected>

Caveat: the abstain case uses a deliberately high floor (0.0189), because the fused score tracks rank and
semantic search always returns neighbours, so even gibberish clears the default floor (see above).

## Prefetch excludes `procedural` by default (`prefetch_kinds`)

Prefetch now sends `kinds: ["episodic", "semantic"]`. Override: env `AMES_PREFETCH_KINDS` > stored panel
config `prefetch_kinds` > default; a comma list of kinds, or `all` to restore the old unfiltered request.
The `agent_memory_recall` tool is unchanged (all kinds). No server change; no doc was deleted, retagged or
re-scoped (the two project-profile blobs belong to their owner).

Before/after, read-only replay of the same 130 prompts against prod with the exact prefetch payload
(`size 5`, `min_score 0.0184`; calibration/replay_kinds.py, 2026-10-12):

| arm | queries | median injected chars | mean | hits | procedural hits |
|---|---|---|---|---|---|
| before (no `kinds`) | 130 | 7970 | 8268 | 635 | 130 |
| after (`episodic`,`semantic`) | 130 | 1743 | 2024 | 506 | 0 |

Median drops 7970 -> 1743 (-78%). (The earlier 8271 -> 1580 figure was computed offline from size-8 replay
hits; this one is measured with the real payload.) No query abstains in either arm.

Relevance check on the 45-hit labelled sample (13 relevant, 11 procedural): 0 of the 11 labelled procedural
hits were relevant. Of the 13 relevant hits, 12 are present in the top 5 in both arms and 1 is absent in
both arms (corpus/ranking drift since labelling; it is not caused by the `kinds` filter). Relevant hits lost
by the change: 0.

Mutation (tests/test_prefetch_kinds.py): default changed to include `procedural` -> 4 failed, 27 passed;
`kinds` never sent -> 6 failed, 25 passed; restored -> 31 passed.

Live smoke (plugin worktree loaded via `load_memory_provider`, `MemoryManager.prefetch_all` +
`build_memory_context_block`, prod recall, query "what did we decide about the kibana eval gate for alertzero"):

    default : body {"size": 5, "min_score": 0.0184, "kinds": ["episodic","semantic"]}
              hits 4 (semantic, episodic, semantic, episodic) | raw chars 2355 | block chars 2579 | 'Project Profile' in block: False
    kinds=all: body {"size": 5, "min_score": 0.0184}
              hits 5 (incl. procedural)                       | raw chars 7994 | block chars 8218 | 'Project Profile' in block: True
