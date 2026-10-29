# Validation and pack integration

Record these gates separately. A later gate does not make an earlier skipped gate pass.

| Gate | Evidence |
|---|---|
| Target | Exact game, loader, Java, wrapper, plugin, mappings and dependency versions |
| Static | Metadata/resources parse; declared IDs, paths and dependencies inspected |
| Build | Wrapper `build` succeeds and the intended JAR exists |
| Data | `runData` runs the intended providers; generated output inspected and packaged |
| Automated behavior | Actual Java/GameTest tests discovered, assertions run, count/result recorded |
| Clean runtime | Intended behavior observed in a clean client and applicable dedicated server |
| Integration | Behavior observed with the exact dependency set in a disposable pack instance |
| Persistence | Save/reload and relevant upgrade/multiplayer behavior observed |

## Optional testable starter

From the toolkit root:

```powershell
.\Minecraft-Forge.ps1 init "<mod project>" --mod-id examplemod --package dev.example.examplemod --name "Example Mod" --with-tests
.\Minecraft-Forge.ps1 doctor --project "<mod project>"
.\Minecraft-Forge.ps1 verify "<mod project>" --starter
.\Minecraft-Forge.ps1 verify "<mod project>" --check
```

Use the same project directory in every command. `verify` runs `runData` in its own Gradle invocation before `runGameTestServer build`, so generated resources are available to the game and final JAR. `--starter` adds the bundled example's exact JSON and named-test assertions. Use plain `verify PATH` after adapting those examples to your feature.

`--with-tests` adds a development mod `<id>_tests` in `src/gameTest`; the main ID is limited to 58 characters to keep that ID within 64. It supplies:

- `ExampleRecipes`: a server-data recipe provider that generates nine example items from one example block, plus the recipe-book advancement.
- `registeredBlockCanBePlaced`: asserts the block's registry ID, places it, and checks its presence.
- `generatedRecipeCraftsOnlyTheExpectedInput`: loads the generated recipe, checks the example-block input and nine-item output, and rejects dirt.

The development mod is loaded for data generation and GameTests. Its sources and empty test structure stay out of the production JAR. The recipe at `data/<id>/recipe/example_items_from_block.json` and advancement at `data/<id>/advancement/recipes/misc/example_items_from_block.json` are packaged. These paths and the provider follow the [NeoForge 1.21.1 recipe documentation](https://docs.neoforged.net/docs/1.21.1/resources/server/recipes/); consult exact target sources before changing API calls.

The run writes `build/reports/gametest/results.xml`. Verification moves any old report aside before running GameTests, requires new actual `testcase` elements and rejects failed/errored/skipped cases. With `--starter`, it also requires both example tests and checks generated JSON against the final JAR. Report count attributes alone cannot prove that tests ran. The older `python scripts/verify_starter.py PATH` checks existing outputs only; it cannot establish freshness.

## Evidence receipts

`verify PATH` hashes the project's source/build inputs before running, then records generated data, selected Java identity, command results/logs and the inspected production JAR. It rejects source changes during the run and generated-data changes after datagen. The latest receipt is `PROJECT/build/mcforge/verification.json`; each run retains its own receipt/logs in `PROJECT/build/mcforge/verification/<run-id>/`. A failed or interrupted run replaces the latest success with a non-passing status. An exclusive lock prevents concurrent verification runs; inspect its owning process before removing an abandoned lock.

`verify PATH --check` is offline and does not build or rerun tests. It requires a passing receipt and rehashes current inputs, generated data, JAR, XML report and logs. Any changed or missing recorded evidence invalidates it. It cannot be combined with `--starter` or `--java-home`; select those when starting a fresh run. The receipt is local evidence, not a signed attestation or a claim about client/pack compatibility.

The supported layout is one toolkit-created Groovy MDK project. Verification hashes local inputs, including libraries, assets and configs; it excludes `.git/`, `.gradle/`, `build/`, Python caches, root `run/`, `run-data/`, `run-gametest/` and workspace progress ledgers. `src/generated/` is recorded separately after datagen. It rejects links, explicit included/applied builds and external literal file paths. Custom tasks computing external paths, external services or mutable dependencies need additional checks; this static inspection is not an attestation of arbitrary build code. Keep logs/receipts out of the shipped mod JAR.

Builds and receipt checks refuse implicit `ORG_GRADLE_PROJECT_*`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, project `systemProp.*` and custom properties/init scripts in the toolkit's shared Gradle cache. These can override the inspected pins; remove them from the selected process/build context before verification. The toolkit preserves their files and values.

Inspect available tasks and the project's run configuration first. Run only the gates relevant to the change, and require each claimed result. `NO-SOURCE`, zero tests, no data providers or an empty generated directory are not behavior coverage. Keep one meaningful regression test for a nontrivial bug; pure business logic should not need a full client boot.

For [NeoForge 1.21.1 GameTests](https://docs.neoforged.net/docs/1.21.1/misc/gametest/), verify namespace discovery and the structure/template used by each test. Assert the requested outcome and a failure case where relevant. A smoke test that only starts the loader proves startup at most.

Use `runClient` for rendering, interaction and visual checks. Use `runServer` for dedicated-server classloading and behavior when applicable; follow the actual generated run's EULA handling. A mod that works in single-player can still accidentally load client-only classes on the dedicated server.

Bare `init` keeps the stock MDK, which contains **zero GameTests**; its `runGameTestServer` can fail until tests are added. `verify` runs datagen/build for this project, records `tests.status = not_configured` and warns that it has no behavioral coverage. It selects the GameTest workflow from the project's `with_tests` marker; custom test setups need their own configured checks. The optional starter's two tests cover only their example slice. Replace their assertions as the mod changes, and run separate client, server, persistence and pack-integration checks for the intended behavior.

## Existing crash baseline

Inventory the active pack read-only and save the report outside the instance. Read the newest crash plus the relevant part of the matching log. Identify the first meaningful exception and any transforms of the failing class; a mod named in a stack trace is an isolation candidate, not automatically the cause.

When pack repair is requested, reproduce in a separate disposable instance with no valuable saves. Change one factor per run, retain a baseline and restoration path, and record exact JAR hashes. A successful launch after removing several mods does not identify which interaction failed. Do not add a new mod to a pack that already crashes and then attribute the crash to the new code.

## Release and handoff

Inspect the final JAR itself: mod metadata, identity/version, generated resources, dependencies and required notices. Exclude development configs, credentials, test logs, run directories, saves and caches. Hash the delivered JAR and identify its target in the release notes.

Report evidence plainly: "build and 3 GameTests passed; client graphics and pack integration untested" is useful. "Compatible with the pack" requires an observed integration result. Keep `STATE.md` and the project's validation record synchronized with the final artifact.
