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

## Fast local loop

From the toolkit root:

```powershell
.\Minecraft-Forge.ps1 gradle "<mod project>" tasks
.\Minecraft-Forge.ps1 gradle "<mod project>" build
.\Minecraft-Forge.ps1 gradle "<mod project>" runData
.\Minecraft-Forge.ps1 gradle "<mod project>" runGameTestServer
```

Inspect available tasks and the project's run configuration first. Run only the gates relevant to the change, and require each claimed result. `NO-SOURCE`, zero tests, no data providers or an empty generated directory are not behavior coverage. Keep one meaningful regression test for a nontrivial bug; pure business logic should not need a full client boot.

For [NeoForge 1.21.1 GameTests](https://docs.neoforged.net/docs/1.21.1/misc/gametest/), verify namespace discovery and the structure/template used by each test. Assert the requested outcome and a failure case where relevant. A smoke test that only starts the loader proves startup at most.

Use `runClient` for rendering, interaction and visual checks. Use `runServer` for dedicated-server classloading and behavior when applicable; follow the actual generated run's EULA handling. A mod that works in single-player can still accidentally load client-only classes on the dedicated server.

The stock MDK contains **zero GameTests**; its `runGameTestServer` can fail until meaningful tests are added. Discovering that task is not a passing test result.

## Existing crash baseline

Inventory the active pack read-only and save the report outside the instance. Read the newest crash plus the relevant part of the matching log. Identify the first meaningful exception and any transforms of the failing class; a mod named in a stack trace is an isolation candidate, not automatically the cause.

When pack repair is requested, reproduce in a separate disposable instance with no valuable saves. Change one factor per run, retain a baseline and restoration path, and record exact JAR hashes. A successful launch after removing several mods does not identify which interaction failed. Do not add a new mod to a pack that already crashes and then attribute the crash to the new code.

## Release and handoff

Inspect the final JAR itself: mod metadata, identity/version, generated resources, dependencies and required notices. Exclude development configs, credentials, test logs, run directories, saves and caches. Hash the delivered JAR and identify its target in the release notes.

Report evidence plainly: "build and 3 GameTests passed; client graphics and pack integration untested" is useful. "Compatible with the pack" requires an observed integration result. Keep `STATE.md` and the project's validation record synchronized with the final artifact.
