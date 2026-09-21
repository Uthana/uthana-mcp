# Partner environment and host acceptance

Use [the acceptance procedure](ACCEPTANCE.md) and [prompt catalog](PROMPT-TESTS.md) for a fixed connector and shared-client revision. Store dated execution reports separately; this checklist is not a certification that every host and capability passed.

## Environment selection

- Without an override, initialization identifies `uthana.com`. An explicit `UTHANA_DOMAIN` (host env, constructor, or checkout `.env` / `.env.local`) identifies exactly that host.
- Use a distinct key and state directory for each configured host. Host-provided environment variables override checkout dotenv files.
- Confirm both normal and catalog clients address only the configured HTTPS origin. Errors and redirects never switch to another environment.
- Verify `UTHANA_API_KEY_FILE` accepts only the documented private regular file and that discovery works without reading credentials. No key or raw credential-file error appears in tool results.
- Confirm pricing-source labels and support references match the configured origin. State and receipts are isolated by origin and credential fingerprint.

## Native host and operating system

Run the following in the actual partner's host on each supported OS, rather than treating a generic stdio bridge as host certification:

1. Install the fixed revision using the locked server-only setup, including paths with spaces.
2. Discover all tools, read the active environment, and make authorized account/character reads.
3. Run one approved generation, inspect returned image frames, trim and export it, and confirm the saved file is usable on that machine.
4. Restart the connector with its persistent state and recover the existing operation without another generation.
5. Verify long-operation progress and host timeouts. The setup guide configures a 1200-second host deadline for image generation; activity notifications may not extend that deadline.
6. Verify upload-directory boundaries and separate credentials and local artifacts per configured host.

Linux stdio coverage does not establish macOS or native coding-host support. Record an untested combination as unverified and explain known limits to an early tester. A non-production host's entitlements and API version can differ from production.

## Release checks

Review/release the shared client before publishing a connector that requires its new capabilities, update the dependency pin and lock, and repeat acceptance against that released dependency. Verify account entitlements and destination imports separately. A local connector release does not establish availability of a hosted multi-account MCP endpoint.

Keep experimental loop/stitch/image behavior and character-upload recovery limitations visible. Public documentation must describe current behavior; private task status, customer fixture identifiers, and raw billing evidence belong in private tracking.
