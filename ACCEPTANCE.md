# MCP acceptance status

This record supports engineering review of the staging MCP. The September 14 [live acceptance record](LIVE-ACCEPTANCE-2026-09-14.md) covers text generation, locomotion, trimming, previews, export, and receipt recovery. It is historical evidence for those cases, not a complete release certification.

## September 15 review fixes

| Finding | Change or disposition |
| --- | --- |
| Character listing exceeds the response cap | Separate 16 MiB catalog read, name filtering, bounded output pages, explicit scope and oversize error |
| Requested upstream pagination | Deferred: staging introspection exposes no paging arguments on `characters`; requires an API and shared-client change |
| Internal documentation references | Removed from package documentation |
| License and metadata | Apache-2.0 license, package author and project URLs; temporary SDK commit pin documented |
| Unresolved character upload | Saved upload name and inspection call; safe processing-error summaries and opaque support reference; recovery preserves uncertain state |
| Historical upload root cause | Unresolved: its receipt discarded the original error details and saved no character ID. The fixture has a skeleton, so an unrigged-file diagnosis is not established. No duplicate submission was made |
| Tool input descriptions | Descriptions on every tool parameter and nested pose field, with units and constraints |
| Long synchronous calls | MCP start, activity, and completion notifications when requested; consistent host deadlines |
| Missing motion/job and file-path errors | Specific not-found mapping for observed missing-resource responses; sanitized local-file errors |
| Global review directive | Removed; optional review prompt retains its own format |
| Documentation language | Short README, canonical workflow rules, consistent terminology and ASCII ranges |
| Stitch sampling | Documented observed root-scale trap and unresolved hip-yaw convention; no fabricated sampling defaults |

The catalog workaround restores the reported account's listing but is not upstream pagination. The 16 MiB bound remains a finite ceiling. True pagination is still a release dependency for larger catalogs.

For ambiguous character processing failures, the server cannot establish whether a partial character was created. It returns inspection guidance instead of treating the failure as a safe retry. A matching character name alone is insufficient to reconcile a request. Exact diagnosis of the historical failed upload requires upstream trace/log inspection or support.

## Verification

`uv run --locked ./test.sh` runs offline protocol, SDK boundary, persistence, validation, formatting, lint, and package-build checks. Tests exercise response-size limits, name-filtered recovery, safe error mapping, complete parameter descriptions, and progress behavior including interruption.

The revision passed 340 offline tests, lint/format checks, and source/wheel builds. The wheel contains the license, author, project URLs, and workflow resource.

Live verification through the revised stdio MCP used staging reads only. `list_characters(limit=1)` returned one result from 46,324 accessible characters. Name filtering returned a bounded recovery page. Missing motion, job, and preview IDs returned `category=not_found`. No model or character-generation submission was made in this pass.

The paid pre-release runbook remains a separate reviewer pass. It covers live execution of all 22 tools and is expected to cost approximately $1.80. That estimate is not a measured charge for this revision.

## Remaining acceptance work

- Rerun the live runbook against the revised MCP and inspect the uploaded character's usability.
- Resolve the historical upload through upstream diagnostics; preserve its existing unknown receipt.
- Add upstream character pagination, then replace the bounded catalog workaround through the shared client.
- Confirm the stitching hip-yaw convention and validate a host pose sampler against scale and facing.
- Verify destination imports, including Roblox Studio, with supported characters.
- Record native coding-host setup and timeout/progress behavior; bridge-based stdio checks alone do not establish every host's behavior.
- Replace the temporary Python-client Git pin after a reviewed release.

A fixed JSON output contract, authenticated remote hosting, and production rollout remain outside this review pass. No deployment or billing-setting change is part of acceptance.
