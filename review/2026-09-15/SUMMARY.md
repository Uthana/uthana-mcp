# Pre-release review of the Uthana MCP — 2026-09-15

Three independent tests of the MCP server at PR #2 head `45c5b61`
(`codex/image-character-loop`, 22 tools), run against the live staging server.
Each test was run by a separate agent that did not write the code. These are
the three tests agreed in the 2026-09-15 team meeting: (1) best-practices
comparison, (2) exercise every tool, (3) language pass. Findings are inputs
for the authoring agent to fix, followed by one human review.

| Test | Report | Verdict |
|---|---|---|
| 1. MCP best practices | [test1-best-practices.md](test1-best-practices.md) | Within community norms; no protocol blockers. Idempotency/safety design exceeds common reference servers. 4 major gaps. |
| 2. Tool-by-tool live test | [test2-tool-test.md](test2-tool-test.md) | 21/22 tools pass end-to-end. 1 blocker, 2 major reliability gaps. Billing exact ($1.75 measured vs $1.745 estimated). |
| 2b. Rerunnable runbook | [test2-RUNBOOK.md](test2-RUNBOOK.md) | 7 phases, ~$1.80 per rerun. Use after every MCP change. |
| 3. Language/copy pass | [test3-language.md](test3-language.md) | Functional for agents; not publishable for humans as-is — ~1 day of editing. 10 rewrites + 14 mechanical style rules included. |

## Fix before partners see the repo (blockers)

1. **`list_characters` cannot succeed on this org** — every limit fails with
   "response exceeded the configured size limit". Paging is applied locally
   after a whole-list upstream fetch under a 2 MiB cap (`operations.py:394`,
   `api.py:31`). Page upstream instead. (Test 2, B1)
2. **Docs leak internals** — team member names, private backend file paths,
   internal tools, and an internal interview log appear in `ACCEPTANCE.md`,
   `README.md`, `LIVE-ACCEPTANCE-2026-09-14.md`. Scrub or exclude these files
   from anything shared externally. (Test 3)
3. **No LICENSE / package metadata**, and the runtime dependency is pinned to
   an unreviewed git commit — becomes a release blocker the moment
   collaborators are added. (Test 1)

## Major

- `upload_character` failed its happy path with an opaque GraphQL error,
  landing in `state=unknown` / "do not resubmit" — and the only inspection
  tool is broken `list_characters`, so an agent gets permanently wedged.
  (Test 2, M2; interacts with B1)
- Long synchronous tools (upload, image-character, loop, stitch; 360–1080 s)
  emit no MCP progress notifications; host timeouts will kill them.
  (Test 1 №2; Test 2 confirms)
- No per-parameter `description` fields reach the wire — units, idempotency
  semantics, and ranges exist only in prose docstrings. (Test 1 №1)
- Error mapping: nonexistent motion IDs surface as outage-like or
  permission-like errors; bad file paths leak raw errno. (Tests 1+2)
- Timeout guidance contradicts itself: docstring says ">360 s", README/
  WORKFLOW say "≥420 s". (Test 3)
- Server `initialize.instructions` force a review behavior ("suggest the
  three most useful improvements") on every session — an internal review
  rule leaked into the product. (Test 3, verified live)

## Notable positives

- Durable `request_id` idempotency verified live on 4 mutating tools:
  `replayed:true`, identical IDs/hashes, no double charge; changed-args
  replays cleanly rejected. Path traversal blocked; tampered bundle hash
  rejected pre-submission.
- Billing is exact: measured balance delta $1.749 vs $1.745 itemized
  estimate, matching published rates × actual generated seconds.
- `create_stitched_motion` works end-to-end: motion `muQ26uyUJS9b` (9.4 s)
  stitched from a trimmed dance intro (`mDFjtFsPJpQB`) + cartwheel
  (`m6L6P35ot1jo`), with real sampled poses extracted from exported GLBs.
  Transition is visually coherent at preview resolution. Two traps for the
  docs: exported rigs carry a ~0.0116 root scale (naive samplers produce
  centimeter positions the schema silently accepts), and the hip-yaw
  convention is unspecified. (Test 2)

## Artifacts created during testing (staging)

Motions `mBBWHrCdL9sE`, `mjL2FVTpZDLc`, `mJbVmLNUMAnq`, `mbUTtMJoLLwQ`,
`mDFjtFsPJpQB` (dance intro trim), `mfQ8JVtAmxLW`, `muQ26uyUJS9b` (stitch),
`mDFMsp4wFA2a` (save_motion); character `c3KJymK79zR2`; jobs `Jg5sqmCkvwhC`,
`JuafQNiN844e`. Total spend ≈ $1.75.
