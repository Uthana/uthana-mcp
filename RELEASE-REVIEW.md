# Open-source MCP release review

This document describes the local MCP release baseline at `main` commit `852497e` plus the release-readiness PR. It is a review handoff, not a release approval. The baseline registers 22 tools and installs the published `uthana` Python client from PyPI. Its primary user flow is a rigged bipedal character, generated motion, preview, and retargeted export. The running animation-agent prototype and its installed skills are separate.

## Changes in this PR

- CI runs the existing formatting, lint, offline tests, and package build on Linux and macOS with Python 3.11 and 3.12. It installs the resulting wheel in a fresh environment outside the checkout and verifies protocol startup, tool discovery, and workflow loading. No production key is configured in CI.
- The installed `uthana-mcp-smoke` command provides the same local protocol check. An explicitly requested `--api-read` adds one read-only account call. The caller supplies the selected environment and credentials; the check creates no assets or jobs.
- Requests to the configured Uthana API host carry the existing `X-Uthana-AppId` convention with value `mcp` and a versioned User-Agent. Authentication, redirects, response parsing, and request receipts remain with the shared client and MCP adapter. Attribution is not proof of every local invocation or a charge.
- README, [first result](FIRST-RESULT.md), and [operational checks](OPERATIONS.md) describe the path to an export and the limits of current evidence.

## Review order

1. Review this PR as the baseline automation and attribution layer. Check the transport host match, the clean-wheel CI step, and the smoke check's read-only behavior and sanitized output. Keep repository CI credentials read-only; no production secrets are needed.
2. Review [#11 Windows support](https://github.com/Uthana/uthana-mcp/pull/11), followed by [#12 text-to-character](https://github.com/Uthana/uthana-mcp/pull/12), which is stacked on #11. Retarget #12 to `main` after #11 merges. The current `main` docs and CI do not claim Windows support.
3. Review [#6 rigging options](https://github.com/Uthana/uthana-mcp/pull/6) and [#7 V1 adapter](https://github.com/Uthana/uthana-mcp/pull/7) independently. #7 does not add an MCP tool.
4. Review [#10 automatic stitching](https://github.com/Uthana/uthana-mcp/pull/10) with its [backend](https://github.com/Uthana/uthana/pull/1748), [Python client](https://github.com/Uthana/uthana-python-client/pull/18), and [JavaScript client](https://github.com/Uthana/uthana-js-client/pull/12). Follow its backend → client → MCP release order; remove its temporary draft-client pin after publication and validate the deployed API before release.
5. [#9](https://github.com/Uthana/uthana-mcp/pull/9) is planning documentation for subsequent hosted and ChatGPT stages. It does not gate local MCP publication.

After integrating selected feature PRs, resolve shared changes in README, workflow, operations, server, and test assertions. Rerun the entire suite and clean-wheel check on the integrated commit. Derive tool counts from the merged code; stitching and text-to-character together would add three tools to the 22-tool baseline.

## Public-release audit

The current tracked tree contains no checked-in `.env` file, key, binary character asset, or generated preview. `LICENSE` is Apache-2.0; package metadata includes the license, entry point, and workflow resource. The baseline `uv.lock` resolves the shared client from PyPI. A targeted scan across reachable commits found no obvious literal private-key blocks or API-key assignments; this is not a comprehensive secret scan.

**History requires an owner decision before making this repository public.** Commit `1088c53` contains `LIVE-ACCEPTANCE-2026-09-14.md`, later removed by `c03f1ac`. It includes staging request/job/motion identifiers, asset hashes, account role and billing observations, and detailed internal test provenance. The current tree no longer contains that report, but making the full Git history public would expose it. Review whether those details are approved for disclosure. If not, prepare a clean public history through the repository owner’s release process; do not treat deletion from the current tree as sufficient.

No redistributable example character has been approved for this repository. `FIRST-RESULT.md` therefore uses the user’s own rigged FBX/GLB, and its procedure is not a recorded production acceptance run. Select and license an example asset before claiming a downloadable reproducible demo. Validate actual export scale, scene contents, and playback in the target engine; Unreal remains pending.

## Remaining decisions

- Decide the exact first-release feature set. The six existing MCP PRs need not merge together. Windows, text-to-character, automatic stitching, and hosted transport remain feature-specific decisions.
- If #12 is included, decide whether the backend already prevents multiple finalizations of one preview/character. The MCP currently deduplicates by finalization request ID, and a second ID submits again. No duplicate charge was established. A durable guard requires concurrency and interruption tests.
- Confirm macOS and Windows native-host behavior before advertising them as validated. CI provides macOS package/protocol coverage after it runs; it does not prove every host integration.
- Connect the read-only smoke check to existing deployment monitoring if desired. A hosted MCP health endpoint and uptime checks belong to the hosted deployment design. Avoid frequent paid generation tests.
- Keep image-to-pose as an API design and pricing decision; the prototype skill is not part of this release.
