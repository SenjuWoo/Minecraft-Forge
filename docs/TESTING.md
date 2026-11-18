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
| neoforge-1.21.1 (and fetched NeoForge before 1.21.5) | After `tests PROJECT` (adds the test mod, a load test and the arena test) or `init --with-tests`; this game version refuses to start a test server with zero tests |
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
- `ArenaTests`: the `arena` template's `STAND` (7, 2, 7) and `FLOOR` positions, and `largeMobStandsUnhurtOnTheArenaFloor`, which keeps a horse there for 100 ticks and requires it alive, unhurt and on the floor.

`--no-examples` (on `init` and `quickstart`, any target) starts without the template's example block, item, creative tab and their names; NeoForge and Forge main classes keep their empty registers and config. With `--with-tests` the test mod keeps its arena, report writer, `LoadSmokeTest` and `ArenaTests`, without the recipe provider and the two example tests; verify it with plain `verify PATH`. Mob-only projects start here instead of deleting examples by hand. If a template ever changes shape, the examples stay and the result carries a warning.

The development mod is loaded for data generation and GameTests. Its sources and empty test structure stay out of the production JAR. The recipe at `data/<id>/recipe/example_items_from_block.json` and advancement at `data/<id>/advancement/recipes/misc/example_items_from_block.json` are packaged. These paths and the provider follow the [NeoForge 1.21.1 recipe documentation](https://docs.neoforged.net/docs/1.21.1/resources/server/recipes/); consult exact target sources before changing API calls.

The run writes `build/reports/gametest/results.xml`. Verification moves any old report aside before running GameTests, requires new actual `testcase` elements and rejects failed/errored/skipped cases. With `--starter`, it also requires both example tests and checks generated JSON against the final JAR. Report count attributes alone cannot prove that tests ran. The older `python scripts/verify_starter.py PATH` checks existing outputs only; it cannot establish freshness.

## Evidence receipts

`verify PATH` hashes the project's source/build inputs before running, then records generated data, selected Java identity, command results/logs and the inspected production JAR. It rejects source changes during the run and generated-data changes after datagen. The latest receipt is `PROJECT/build/mcforge/verification.json`; each run retains its own receipt/logs in `PROJECT/build/mcforge/verification/<run-id>/`. A failed or interrupted run replaces the latest success with a non-passing status. An exclusive lock (`build/mcforge/verification.lock`, holding the run id and process id) prevents concurrent verification runs. When the recorded process no longer exists (a killed run), the next `verify` replaces the lock and records a warning in its receipt; a lock whose process is alive, or that cannot be read, is refused with its path.

`verify PATH --check` is offline and does not build or rerun tests. It requires a passing receipt and rehashes current inputs, generated data, JAR, XML report and logs. Any changed or missing recorded evidence invalidates it. It cannot be combined with `--starter` or `--java-home`; select those when starting a fresh run. The receipt is local evidence, not a signed attestation or a claim about client/pack compatibility.

The supported layout is one toolkit-created Groovy MDK project. Verification hashes local inputs, including libraries, assets and configs; it excludes `.git/`, `.gradle/`, `build/`, Python caches, root `run/` and every root `run-*` game directory (`run-data/`, `run-gametest/`, `run-devshots/` ...), and workspace progress ledgers. Keep a run's game directory under one of those names so worlds, screenshots and logs written between `verify` and `verify --check` never invalidate the receipt. `src/generated/` is recorded separately after datagen. It rejects links, explicit included/applied builds and external literal file paths. Custom tasks computing external paths, external services or mutable dependencies need additional checks; this static inspection is not an attestation of arbitrary build code. Keep logs/receipts out of the shipped mod JAR.

Builds and receipt checks refuse implicit `ORG_GRADLE_PROJECT_*`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, project `systemProp.*` and custom properties/init scripts in the toolkit's shared Gradle cache. These can override the inspected pins; remove them from the selected process/build context before verification. The toolkit preserves their files and values.

Inspect available tasks and the project's run configuration first. Run only the gates relevant to the change, and require each claimed result. `NO-SOURCE`, zero tests, no data providers or an empty generated directory are not behavior coverage. Keep one meaningful regression test for a nontrivial bug; pure business logic should not need a full client boot.

For [NeoForge 1.21.1 GameTests](https://docs.neoforged.net/docs/1.21.1/misc/gametest/), verify namespace discovery and the structure/template used by each test. Assert the requested outcome and a failure case where relevant. A smoke test that only starts the loader proves startup at most.

Use `runClient` for rendering, interaction and visual checks. Use `runServer` for dedicated-server classloading and behavior when applicable; follow the actual generated run's EULA handling. A mod that works in single-player can still accidentally load client-only classes on the dedicated server.

Bare NeoForge 1.21.1 `init` keeps the stock MDK, which contains **zero GameTests**; its `runGameTestServer` refuses to start until a test exists (`tests PROJECT` adds one). `verify` runs datagen/build for this project, records `tests.status = not_configured` and warns that it has no behavioral coverage. It selects the GameTest workflow from the project's `with_tests` marker; custom test setups need their own configured checks. The optional starter's two tests cover only their example slice. Replace their assertions as the mod changes, and run separate client, server, persistence and pack-integration checks for the intended behavior.

## Entity and AI GameTests (NeoForge 1.21.1)

- The starter's `empty` template is 3x3x3: a mob spawned there is boxed in and AI tests fail for the wrong reason. `--with-tests` and `tests` also ship `arena` (15x7x15, smooth-stone floor, air above): `@GameTest(template = "arena", timeoutTicks = 200)` with `@PrefixGameTestTemplate(false)` on the holder.
- **Stand at y = 2.** `GameTestHelper` positions are relative to the structure *block*, and the template is placed one block above it (the structure block's default offset is 0, 1, 0; `StructureUtils.getStructureOrigin`). Relative y = 1 is the arena floor itself. Use `ArenaTests.STAND` (`new BlockPos(7, 2, 7)`, the centre on the floor) or offsets from it. A mob spawned at y = 1 sits inside the floor and takes suffocation damage until it dies; tests that pass on their first tick never notice, multi-tick ones (breeding, healing over time) fail. The shipped `largeMobStandsUnhurtOnTheArenaFloor` guards this. To debug a position, log `helper.relativeVec(mob.position())` and the block at the eyes.
- GameTest plots are placed millions of blocks from the origin. There, float precision breaks pathfinding (paths come back empty) and line-of-sight rays. Test the behaviour at melee or cast range, call `setTarget` directly, and keep pathing out of the assertion; skip line-of-sight checks for point-blank actions in the mod itself.
- Use husks, not zombies, as attackers: zombies burn in the test's daylight, so "the monster lost health" passes without your mob doing anything. Give dummies `setNoAi(true)` so only the actor under test acts.
- Assert the outcome with `succeedWhen(() -> assertTrue(...))` and a failure message carrying the value (`"not healed: " + v.getHealth()`). Add the negative case (friendly fire is rejected, health unchanged) next to the positive one.
- `runAfterDelay(ticks, ...)` stages a provocation after spawn settles.
- Breeding: `canParent()` needs tame (for horses), grown (not a baby), full health and in love; two parents within 3 blocks breed after the breed goal's 60-tick timer even where pathfinding is broken.
- **Mock players are not in the level.** `GameTestHelper.makeMockPlayer` creates a `Player` that is never added, so `TamableAnimal.getOwner()` (a level lookup by UUID) returns null: `isOwnedBy(player)` is false and owner-only interactions silently refuse. `makeMockServerPlayerInLevel()` works; it is marked deprecated for removal in 1.21.1 and is in creative mode, so `ItemUtils.createFilledResult` keeps the empty container in hand and puts the filled item in the inventory: assert on the inventory. Remove that player from the `PlayerList` when the test ends, or hostile mobs in later tests path toward it.
- **A movement test that passes in 2 ticks is probably not testing movement.** Assert the start condition (distance) and a minimum elapsed tick count, then `succeedWhen` the end condition.
- Natural spawns without a world: after an `add_spawns` biome modifier, assert `biome.getMobSettings().getMobs(MobCategory.CREATURE).unwrap()` contains your type with the expected weight and group sizes (the modified settings are visible there), plus one biome that must not have it.

## Client screenshot automation

`client_load` and looks are only proven in a client. A development-only client run can stage scenes, save screenshots and quit with nobody at the keyboard, which is far cheaper than asking the user to look. Put it in the `gameTest` source set so it never reaches the JAR.

**Generated (NeoForge 1.21.1):** `devshots PROJECT [--subject mymod:cave_boar]` writes two files into the test mod and a `devShots` client run into `build.gradle` (the project needs the test mod: `tests PROJECT` or `init --with-tests`):

- `DevShots.java`, the engine: creates a flat creative world (it also dismisses the first-launch accessibility screen of a new game directory), then plays a script one step at a time and quits. `devshots --force` replaces it.
- `DevScenes.java`, the script, yours and never overwritten: scenes built from steps. Starter scenes: `turntable` (ten shots), `uv` (orientation proof with the UV test texture, including straight above and below) and `night`.

```java
if (DevShots.wanted("attack")) {
    s.shotFramed("attack_before", 30f, 10f, 1.0);
    s.burst("attack", e -> ((MyMob) e).triggerAnim("action", "attack"), 2, 6, 10, 14);   // server-side start, frames by tick
    s.server(20, e -> ((MyMob) e).setTarget(null));
    s.then(1, mc -> DevShots.trace("reach", "tick=6 dist=1.82"));                          // a number for devlog
}
```

Script steps: `cmd`, `waitTicks`, `shotAt(name, yaw, pitch, distance, aimY)`, `shotFramed(name, yaw, pitch, factor)`, `server(wait, action)` (runs on the integrated server for the subject), `burst(name, start, ticks...)`, `then(wait, action)`. A step runs its action and then waits `wait` ticks, so a wait of n puts the next step n + 1 ticks later; a wait of 0 gives one step per tick (moving a subject a fixed distance every tick).

`verify PROJECT --client [--scenes turntable,attack]` builds, runs the client, requires the driver's `MCFORGE-DEVSHOTS done N` marker and N fresh screenshots, copies them into the receipt folder and records `client_load: passed`. `--scenes` limits the run to named scenes (it writes `run-devshots/scenes.txt`); a full run before release, single scenes while iterating. The receipt warns when three or more consecutive screenshots are byte-identical: clicking or focusing the game window during a run freezes the camera while the script keeps going. A display is required, so CI cannot run it; `gameplay` stays `not_run`. The first run downloads the game assets and can take several minutes.

**Gate the log, not only the pictures:** `devlog PROJECT [--rules FILE] [--gate NAME]` reads the run's log. Without rules it fails on an unfinished script, exceptions that name the mod or its libraries, sound events without a sound and missing models or textures of the mod. With rules (default `PROJECT/devlog-rules.json`) it also checks `MCFORGE-TRACE kind key=value ...` lines that the scenes (`DevShots.trace`) and dev-flagged mod code (`kit PROJECT trace`, enabled by `-Dmcforge.trace=true`, which the devShots run sets) print:

```json
{"gates": {"final": [
  {"kind": "spring", "where": {"id": "physics"}, "group_by": "name", "pick": "last", "field": "peak", "min": 0.65, "max": 0.85},
  {"kind": "chain", "skip": {"id": "teleport*"}, "field": "stretch", "min": 0.9, "max": 1.15},
  {"kind": "spawn", "field": "dist", "max": 0.25},
  {"kind": "fps", "compare": {"field": "fps", "a": {"scene": "eight"}, "b": {"scene": "one"}, "min_ratio": 0.6}, "severity": "warn"}]}}
```

Numbers worth tracing: spring peaks against their clamps, chain stretch, the distance between where the server spawned something and where the client drew its source at that tick, rendered levels against synced values, hit targets reached, frames per second with one and with eight instances. Its output also summarises every trace kind (count, min, max, last per field), which is enough to pick thresholds.

The world of the run is flat, creative and has structure generation off: fast, and nothing wanders into the shots. `verify PROJECT --client --world normal` creates normal terrain with structures on, for worldgen proof (`guide worldgen`): the engine's `locate(dimension, structure, radius, heightAbove)` step searches a bounded radius, logs a `locate` trace and flies the camera there; `DevShots.NORMAL_WORLD` tells scenes which world they are in (flat-world coordinates such as y = -60 do not apply).

Harness habits that removed flaky runs: build the script once (a driver that built it twice spawned every subject twice in the same spot and looked like a rendering bug); remove test entities with `discard()`, not `kill()` (no death clip, drops or sounds leaking into the next step); pin wandering helpers (NoAI, or a fixed position every tick) and keep test fixtures away from the arena edge, where chunks may not tick; use husks instead of zombies for daylight fights and set the difficulty the test assumes; give long suites their own batch.

A second run block can load copies of the target pack's mods beside yours (a `runPackShots` with its own game directory and a `mods` folder of copied JARs): it shows conflicts with animation, model and physics mods before the user does. Other mods' first-join screens pause the world; switch them off in that run folder's config.

Making scenes repeatable: a NoAI subject, one server action per step, a fresh patch of ground away from earlier scenes, other entities removed, hold the subject's yaw (an idle mob's body drifts toward its head). Do not run two clients, or a client beside another GPU job, when you measure frame rate or timing.

The hand-written pattern below is what the generated engine does, plus the techniques for richer scenes.

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

The `run-devshots` game directory is excluded from verification inputs (every root `run-*` folder is); `project.file('build/devshots')` works too and is removed by `clean`.

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
    if (tick == 0) mc.options.pauseOnLostFocus = false;    // an unattended window loses focus and pauses
    if (mc.screen instanceof PauseScreen) mc.setScreen(null);
    tick++;   // then run scripted steps by tick: commands, camera moves, screenshots, finally mc.stop()
}
static void cmd(String c) { Minecraft.getInstance().player.connection.sendCommand(c); }
static void shot(String n) { var mc = Minecraft.getInstance(); Screenshot.grab(mc.gameDirectory, n + ".png", mc.getMainRenderTarget(), m -> {}); }
```

- Without the two pause lines above, frames capture the pause menu as soon as the window loses focus.
- `time set` reaches the sky and light a few ticks late: shots taken 4 ticks after it were still at night; wait about 20 ticks.
- First steps: `gamerule doDaylightCycle false`, `time set 6000`, `gamerule doMobSpawning false`, `weather clear`, `gamemode spectator`, `options.hideGui = true`; flat world surface is y = -60.
- Camera: `tp @s x y z yaw pitch` with `yaw = atan2(-dx, dz)`, `pitch = -atan2(dy, horizontal)` toward the subject. `tp` places the feet; the eye is 1.62 higher. For a 2.4-block mob at FOV 70 in a 1600x1000 window, close-ups need about 1.7-2.2 blocks; at 5-6 blocks the subject is small.
- Richer scenes that worked: animations triggered on the integrated server thread (`triggerAnim`) for deterministic action frames, a UV-ramp texture override for orientation checks, a `/fill` water pool for swimming, a night pass for glow layers, and `/playsound` for every sound event; about 100 screenshots plus a log scan replaced most manual checks.
- Expected dev-run noise: `Missing sound for event: minecraft:...` warnings can appear in dev clients; filter them and look only for `Unable to play unknown soundEvent` with your namespace.
- Turntable: front, both three-quarters, both sides, back, plus close-ups; `summon ... {NoAI:1b,Rotation:[180f,0f]}` for posed shots. Burst frames (`shot` every 2 ticks) for each action; a hostile dummy with `effect give ... resistance` keeps a fight going.
- Structures and villages: `place structure minecraft:village_plains x y z` (a non-spectator player must be nearby for chunk ticking).
- **Entity tags exist only on the server.** `Entity#getTags()` on the client is empty, so selecting subjects by tag in the client tick finds nothing. Select by position or UUID on the client, or act through the integrated server, where tags work: `var srv = mc.getSingleplayerServer(); srv.execute(() -> srv.overworld().getEntitiesOfClass(T.class, box, e -> e.getTags().contains("subject")).forEach(...))`.
- **Drive state; do not wait for AI.** Through the integrated server: set velocity every tick for walk/run frames (`setDeltaMovement` with a fixed yaw), call state methods directly (`setEating(true)`, `standIfPossible()`), equip by command (`item replace entity @e[tag=x] horse.saddle with saddle`, `... armor.body with leather_horse_armor[dyed_color={rgb:6467752}]`), put the camera player on a mount with `ride @s mount @e[tag=x,limit=1]` plus `options.setCameraType(...)`, and summon babies with `{Age:-24000}`. Every frame is then reproducible.
- Log numeric state too (spring offsets, health, positions) to `latest.log`; numbers settle tuning questions screenshots cannot.
- Run it in the background with a timeout; read the PNGs (`run-devshots/screenshots/`) and the log. Report what was looked at; it is still not a pack-integration test. `verify` keeps `client_load` and `gameplay` at `not_run`: a screenshot run is evidence you report next to the receipt, not part of it.

## Existing crash baseline

Inventory the active pack read-only and save the report outside the instance. Read the newest crash plus the relevant part of the matching log. Identify the first meaningful exception and any transforms of the failing class; a mod named in a stack trace is an isolation candidate, not automatically the cause.

When pack repair is requested, reproduce in a separate disposable instance with no valuable saves. Change one factor per run, retain a baseline and restoration path, and record exact JAR hashes. A successful launch after removing several mods does not identify which interaction failed. Do not add a new mod to a pack that already crashes and then attribute the crash to the new code.

## Release and handoff

Inspect the final JAR itself: mod metadata, identity/version, generated resources, dependencies and required notices. Exclude development configs, credentials, test logs, run directories, saves and caches. Hash the delivered JAR and identify its target in the release notes.

Report evidence plainly: "build and 3 GameTests passed; client graphics and pack integration untested" is useful. "Compatible with the pack" requires an observed integration result. Keep `STATE.md` and the project's validation record synchronized with the final artifact.
