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

## Evidence tiers per target

Every receipt carries `tiers`: `compile`, `package`, `server_load`, `client_load`, `gameplay`. The toolkit can run the first three headlessly; `client_load` and `gameplay` stay `not_run` until a person or a client automation observes them.

| Target | How `verify` reaches `server_load` |
|---|---|
| fabric-* | Always: the scaffold carries Fabric's official game-test wiring and a `LoadSmokeTest`; `build` runs the game-test server and the receipt records the actual test cases |
| neoforge-1.21.1 (and fetched NeoForge before 1.21.5) | After `tests PROJECT` (adds the test mod and one load test) or `init --with-tests`; this game version refuses to start a test server with zero tests |
| neoforge-26.3, forge-1.20.1, forge-26.3 | `verify PROJECT --load` boots the game-test server after the build |

`server_load` passes only when the log shows the server started; Gradle's exit code alone is not accepted (NeoForge 1.21.1 exits 0 after refusing to start).

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

Bare NeoForge 1.21.1 `init` keeps the stock MDK, which contains **zero GameTests**; its `runGameTestServer` refuses to start until a test exists (`tests PROJECT` adds one). `verify` runs datagen/build for this project, records `tests.status = not_configured` and warns that it has no behavioral coverage. It selects the GameTest workflow from the project's `with_tests` marker; custom test setups need their own configured checks. The optional starter's two tests cover only their example slice. Replace their assertions as the mod changes, and run separate client, server, persistence and pack-integration checks for the intended behavior.

## Entity and AI GameTests (NeoForge 1.21.1)

- The starter's `empty` template is 3x3x3: a mob spawned there is boxed in and AI tests fail for the wrong reason. `--with-tests` also ships `arena` (15x7x15, smooth-stone floor, air above): `@GameTest(template = "arena", timeoutTicks = 200)` with `@PrefixGameTestTemplate(false)` on the holder. Positions inside it are relative (`new BlockPos(7, 1, 7)` is the centre, on the floor).
- GameTest plots are placed millions of blocks from the origin. There, float precision breaks pathfinding (paths come back empty) and line-of-sight rays. Test the behaviour at melee or cast range, call `setTarget` directly, and keep pathing out of the assertion; skip line-of-sight checks for point-blank actions in the mod itself.
- Use husks, not zombies, as attackers: zombies burn in the test's daylight, so "the monster lost health" passes without your mob doing anything. Give dummies `setNoAi(true)` so only the actor under test acts.
- Assert the outcome with `succeedWhen(() -> assertTrue(...))` and a failure message carrying the value (`"not healed: " + v.getHealth()`). Add the negative case (friendly fire is rejected, health unchanged) next to the positive one.
- `runAfterDelay(ticks, ...)` stages a provocation after spawn settles.

## Client screenshot automation

`client_load` and looks are only proven in a client. A development-only client run can stage scenes, save screenshots and quit with nobody at the keyboard, which is far cheaper than asking the user to look. Put it in the `gameTest` source set so it never reaches the JAR.

`build.gradle`:

```groovy
neoForge { runs { devShots {
    client(); gameDirectory = project.file('run-devshots')
    systemProperty "${mod_id}.devshots", 'true'
    programArguments.addAll('--width', '1600', '--height', '1000')
    sourceSet = sourceSets.gameTest
    loadedMods = [neoForge.mods[project.mod_id], neoForge.mods["${project.mod_id}_tests"]]
} } }
```

In the test mod constructor: `if (System.getProperty("<mod>.devshots") != null && FMLEnvironment.dist.isClient()) NeoForge.EVENT_BUS.addListener(DevShots::onClientTick);`. The driver (verified on 1.21.1):

```java
public static void onClientTick(ClientTickEvent.Post event) {
    Minecraft mc = Minecraft.getInstance();
    if (mc.level == null || mc.player == null) {
        if (!requested && mc.screen instanceof TitleScreen title) {           // create a fresh flat creative world
            requested = true;
            String name = "devshots_" + System.currentTimeMillis();
            LevelSettings s = new LevelSettings(name, GameType.CREATIVE, false, Difficulty.EASY, true, new GameRules(), WorldDataConfiguration.DEFAULT);
            mc.createWorldOpenFlows().createFreshLevel(name, s, new WorldOptions(1L, false, false),
                    ra -> ra.registryOrThrow(Registries.WORLD_PRESET).getHolderOrThrow(WorldPresets.FLAT).value().createWorldDimensions(), title);
        }
        return;
    }
    tick++;   // then run scripted steps by tick: commands, camera moves, screenshots, finally mc.stop()
}
static void cmd(String c) { Minecraft.getInstance().player.connection.sendCommand(c); }
static void shot(String n) { var mc = Minecraft.getInstance(); Screenshot.grab(mc.gameDirectory, n + ".png", mc.getMainRenderTarget(), m -> {}); }
```

- First steps: `gamerule doDaylightCycle false`, `time set 6000`, `gamerule doMobSpawning false`, `weather clear`, `gamemode spectator`, `options.hideGui = true`; flat world surface is y = -60.
- Camera: `tp @s x y z yaw pitch` with `yaw = atan2(-dx, dz)`, `pitch = -atan2(dy, horizontal)` toward the subject (eye height 1.62).
- Turntable: front, both three-quarters, both sides, back, plus close-ups; `summon ... {NoAI:1b,Rotation:[180f,0f]}` for posed shots. Burst frames (`shot` every 2 ticks) for each action; a hostile dummy with `effect give ... resistance` keeps a fight going.
- Structures and villages: `place structure minecraft:village_plains x y z` (a non-spectator player must be nearby for chunk ticking).
- Log numeric state too (spring offsets, health, positions) to `latest.log`; numbers settle tuning questions screenshots cannot.
- Run it in the background with a timeout; read the PNGs (`run-devshots/screenshots/`) and the log. Report what was looked at; it is still not a pack-integration test.

## Existing crash baseline

Inventory the active pack read-only and save the report outside the instance. Read the newest crash plus the relevant part of the matching log. Identify the first meaningful exception and any transforms of the failing class; a mod named in a stack trace is an isolation candidate, not automatically the cause.

When pack repair is requested, reproduce in a separate disposable instance with no valuable saves. Change one factor per run, retain a baseline and restoration path, and record exact JAR hashes. A successful launch after removing several mods does not identify which interaction failed. Do not add a new mod to a pack that already crashes and then attribute the crash to the new code.

## Release and handoff

Inspect the final JAR itself: mod metadata, identity/version, generated resources, dependencies and required notices. Exclude development configs, credentials, test logs, run directories, saves and caches. Hash the delivered JAR and identify its target in the release notes.

Report evidence plainly: "build and 3 GameTests passed; client graphics and pack integration untested" is useful. "Compatible with the pack" requires an observed integration result. Keep `STATE.md` and the project's validation record synchronized with the final artifact.
