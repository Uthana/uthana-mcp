# Contributor and agent guide

Apply these conventions to new code and the code you change. Preserve existing public interfaces and keep unrelated typing or style migrations out of a focused change.

## Python style

- Put imports at module level. Import inside a function only to resolve a circular dependency or avoid a measurable startup cost.
- Use keyword-only arguments when a function has more than two parameters or has parameters that are easy to swap. Preserve compatibility when changing an existing callable.
- Annotate new functions and methods with argument and return types when known. Do not add types throughout unrelated existing code just to satisfy a local change.
- Treat untrusted JSON and provider payloads as `object` until validated. Check container types before accessing fields. Use `type(value) is int` for counts when booleans must be rejected; a failed check leaves the value unknown.
- Use Pydantic models for structured input schemas owned by this package, with `extra="forbid"` and `strict=True`. Persist `model_dump()` when storing a model as JSON. A boolean or numeric string must not silently become a billed or stored count.
- Use `TypedDict` for dictionaries this code builds and later updates. Declare optional keys with `NotRequired`. When branches return variations of the same record, build the shared fields once, add the differing fields, and return that record.
- Put shared keys in a base `TypedDict` and extend it for related records. Unpack a typed shared record rather than rebuilding it with a dict comprehension. Preserve a present key even when its value is `None`, and narrow optional keys explicitly before accessing them.
- Prefer f-strings, including numeric formatting such as `{count:,}` or `{ratio:.2%}`. Logging calls should keep the logger's deferred format arguments.
- Use `pathlib.Path` for filesystem paths. Convert strings at the boundary, pass `Path` objects through, and convert back only where an API requires a string. Use `PurePosixPath` for virtual paths that are independent of the operating system.
- Put fixed limits in named module-level constants. Name each constant for what it bounds; keep shared limits in one place.
- Prefer a clear comprehension for building a collection. Use `next()` on a generator when only the first match is needed.
- Prefer early returns for cases that leave the function. When checks share a return, continuation, or error, combine them. Two or three simple comparisons may stay inline; for a long condition, name each piece for the rule it represents and combine those names. Prefer semantic names over splitting one condition into repeated branches. Keep type-narrowing guards inline before reading fields or computing dependent predicates.

  ```python
  has_wrong_origin = scope != expected_origin
  is_request_pending = state == "pending"
  if has_wrong_origin or is_request_pending:
      return None
  ```

- Give a nested `any()` or `all()` a helper or variable when its predicate is complicated. Keep checks that narrow a type in the condition where that type is used.
- Use `:=` when a lookup is tested and its result is reused, provided it keeps the condition readable. Do not introduce an assignment expression whose name is never read again.
- Let unexpected errors propagate. Catch an exception when the failure is expected and recovery or another code path is required. At an external boundary, redact credentials and private provider details while preserving a useful error category.
- Write error messages that say what failed and what to do next. Identify the record, field, or operation and include safe lookup values when useful, for example, "No character_id found matching {character_id}." For validation errors, state the expected shape, range, or step order. Use distinct errors for distinct failures rather than a generic "incomplete result" or "No resource found." Never include credentials or private provider details, and do not suggest resubmitting a paid operation when its outcome is unknown.

## Tests and coverage

Use the checked-in tools and settings rather than introducing a second formatting or test configuration:

```sh
uv sync --locked
uv run --locked bash ./test.sh
```

The verification script runs Ruff, Black, isort, Flake8, pytest with coverage, and package builds. Python formatting uses a 120-character line length. Coverage must stay at or above the configured 85% gate, including subprocess coverage. There is no separate mypy gate configured; do not claim type checking ran when it did not.

- Add focused regression tests for fixed bugs and meaningful behavior changes. Cover invalid inputs, error paths, replay/recovery, and compatibility where relevant. Assert observable behavior rather than reproducing the implementation in the test.
- Keep the normal suite offline and deterministic. Mock external services; live checks must be explicitly configured and must not silently use production credentials or spend credits.
- Check the missing-coverage report for changed paths. Improve coverage of important branches rather than chasing a percentage with trivial tests. Do not lower thresholds or add exclusions to hide a failure.
- Exercise platform-specific behavior on its native operating system in CI. Skip a fixture only when the platform cannot provide it, with a clear reason; do not suppress a failure in supported behavior.
- Run focused checks while developing, then the complete applicable verification before handing off executable changes. For documentation-only changes, check accuracy, links, and formatting without inventing redundant tests.

## Changes and review

- Prefer backward-compatible changes. Treat removed fields, required new arguments, changed semantics, and reduced limits as compatibility changes; document their effect on callers.
- Keep documentation alongside the behavior it describes. Keep temporary release history, personal handoffs, and test-run transcripts out of published documentation.
- Review the full diff for bugs, security issues, unnecessary abstraction, duplicated logic, and generated boilerplate. Remove stale or misleading claims, and preserve checks that enforce real behavior.
- Fix actionable findings and rerun affected checks after the final fix. State what passed, what was not checked, and which findings were judged non-actionable. Distinguish manual review from automated review.
- Keep pull request descriptions focused on the problem, resulting behavior, compatibility, and verification. Do not claim a check covers components it did not exercise.
- Do not merge or publish without authorization.

## Boundary validation and style reviews

- Start boolean variable names with `is` or `has`, using the language’s casing: `is_valid_motion`, `has_frame_range` in Python; `isValidMotion`, `hasFrameRange` in TypeScript. Prefer names that read as a clear predicate. Preserve published parameter and field names for compatibility.
- Name predicates for the domain rule they express, then combine names at a shared error, return, or continuation. Keep simple type-narrowing guards inline before field access. Do not compute an unsafe or expensive predicate eagerly just to give it a name.
- Treat untrusted values as `object` in Python or `unknown` in TypeScript until validated. Build owned normalized records with declared types; a cast is not runtime validation. Keep any necessary assertion local to the checks that justify it.
- Distinguish omitted fields from explicit null, zero, and false. Apply defaults only where the contract permits them. Validation must not mutate caller-owned nested data.
- Name domain limits and non-obvious numeric tolerances, including units. Keep equivalent cross-language contracts aligned with shared acceptance, rejection, and normalization fixtures.
- Keep runtime validation in normal control flow; do not use Python `assert` for caller input, permissions, or side-effect preconditions. Assertions may narrow already-proven internal invariants, but prefer a type design that avoids repeating the proof.
- Use module-level imports, including TypeScript `import type`. Local imports need a circular-dependency or measurable startup-cost reason. Keep module summaries accurate when a file serves both current and legacy interfaces.
- Preserve published signatures, error categories, unknown-outcome recovery, and side-effect order during style changes. Do not retrofit unrelated existing code. Add tests for changed behavior or meaningful gaps, not for a cosmetic rewrite of the same implementation.

Use the shared SDK types for SDK calls and core results. Pydantic models own the MCP tool schema; retain normalization needed for durable receipt fingerprints rather than silently changing numeric/default representation during a style refactor.
