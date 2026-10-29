# Contributing

This is an early NeoForge-first workbench. Open an issue before a large provider, architecture or dependency change. Small reproducible fixes and documentation corrections are welcome.

Use Python 3.11+, a JDK21 and ripgrep for source search. No Python packages are required. Read AGENTS.md and the guide for the affected workflow. Preserve the pinned template and third-party notices; never modify launcher instances during tests.

Run `python -m mcforge self-test`, `python scripts/package.py` and `python scripts/verify_package.py`. For scaffold/build changes, create a disposable project with `init`, inspect it with `doctor --project PATH`, then run `verify PATH` and the relevant runtime checks. Keep one meaningful regression for changed behavior. Report the exact target, commands and results in the PR; distinguish build success from gameplay proof.

Keep the change focused. Do not add a background service, mandatory account, global configuration edit or new dependency without a concrete workflow that needs it. Never include saves, launcher/account files, credentials, full private logs or installed mod JARs in an issue or commit.

For testable-scaffold changes, use `init ... --with-tests`, run `verify PATH --starter`, then `verify PATH --check`. Keep the provider/test mod out of the production JAR and validate actual nonempty XML results. The starter assertions are deliberately specific to the bundled example slice; update them when changing that slice. The older `scripts/verify_starter.py` helper inspects existing outputs only and cannot establish a fresh run.

Target inspection must remain offline. `updates PATH` is an explicit read-only network command; candidates are not validated upgrades. Preserve legacy lock behavior and reject ambiguous/dynamic pin syntax rather than executing a build during inspection. Changes to verification must cover stale input/output rejection and failure/interruption invalidating old success. Full build logs and receipts stay in the disposable project's `build/mcforge/`.

Template refreshes are maintainer actions: update the immutable commit in scripts/vendor_mdk.py, verify official hashes/licenses, regenerate vendor/manifest.json, and test a real build. Do not change a loader, mappings or wrapper version independently without validation.

Original contributions are accepted under the repository's MIT license. Preserve third-party licensing. Fabric/Forge expansion is planned, not implemented.
