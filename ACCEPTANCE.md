# MCP acceptance procedure

Use this procedure to evaluate a specific connector revision and coding host. Record outcomes separately from these reusable instructions. Passing offline tests does not establish live API access, animation quality, or successful import into another application.

## Prepare

Record the connector and Python-client revisions, host/version, OS, active API domain, and enabled capabilities. Use a tester-controlled account, an explicitly authorized spending limit, and a persistent private state directory. Keep keys, private asset identifiers, billing records, and raw media outside public reports.

Create or select accessible fixtures using [the prompt catalog](PROMPT-TESTS.md). A fixture ID from another account or environment is not portable. Before each paid case, inspect current prices and the requested quantity. Estimates are not measured charges; never infer zero cost from a missing value.

## Offline checks

```sh
uv sync --locked
uv run --locked ./test.sh
```

These run protocol, shared-client boundary, validation, recovery, formatting, lint, and packaging checks without calling Uthana models. Record the actual result for the revision under test, rather than keeping a fixed test count in this procedure.

## Live checks

1. Discover the tools and read `uthana://workflow` without credentials. Then configure the selected environment's key, confirm the reported environment, and read account usage and characters. Start with `list_characters(limit=1)` and report its bounded catalog scope.
2. Run the prompt catalog's generation cases within the approved budget. Poll asynchronous jobs to a usable motion ID, distinguish terminal failures from unresolved results, and record the chosen model and rationale.
3. Read native metadata and inspect preview frames before, during, and after relevant events. Judge action fidelity separately from successful tool execution. Report frame indexes when preview timing is unavailable.
4. Trim and inspect a separate result, leaving its source intact. Register a valid editor-produced GLTF when that fixture is available. Verify source identity and returned result IDs.
5. Upload a selected video and rigged character; inspect their actual usability. Exercise image creation, loop, and stitch only with required entitlements, fixtures, and host skills. An experimental case with unmet prerequisites is blocked, not passed.
6. Export the requested character, format, frame rate, and mesh options. Inspect the actual export; native previews do not show export-only changes. Import into the named destination to claim destination compatibility.
7. Restart the connector and inspect/replay completed requests with their original IDs and arguments. Verify that generation is not submitted again. On an unknown outcome, inspect the receipt/job and reconcile before retrying. Do not intentionally interrupt paid work without authorization.
8. Check missing resource and invalid local-file behavior. Errors must be actionable and avoid revealing credentials or raw filesystem details. With separately authorized accounts, verify private assets cannot be accessed across account boundaries.
9. In each supported native host, verify image display, usable export paths, long-call deadlines, progress, restart recovery, and input-directory restrictions. Generic stdio tests do not establish native host behavior. Allow at least 420 seconds for character upload, loop and stitch, and 1080 seconds for image creation; transfers may need longer.

## Record results

For each catalog case record: prompt variant, prerequisite fixture references, expected behavior, observed tool sequence, API/protocol result, visual result, destination-import result if relevant, estimate, measured usage if attributable, and pass/fail/blocked with a reason. Record exact revisions and any operation/job IDs in private evidence.

A connector case can pass while a generated motion fails its quality rubric. Do not present a model's missed action as a successful user outcome or assume it is necessarily a connector defect. Conversely, unsupported capabilities should be explained without fabricated execution.

## Limitations to exercise

- Character listing reads a catalog capped at 16 MiB before filtering locally. Smaller output pages do not make the upstream read smaller. Motion search covers a bounded recent window.
- An ambiguous character upload may have created a partial asset. Use receipt inspection guidance and compare catalog candidates; a matching name alone does not prove completion or authorize a duplicate upload.
- Stitching requires a validated host sampler, correct ancestor scale, and calibrated facing. See [the stitching contract](STITCHING.md). Typed inputs alone do not establish correct poses.
- Model entitlements and export eligibility vary by account. Normal-user behavior must be tested separately from administrator behavior.
- The temporary client commit pin, supported environments, and platform requirements are described in [README.md](README.md). Validate the released dependency before advertising a new connector release.
