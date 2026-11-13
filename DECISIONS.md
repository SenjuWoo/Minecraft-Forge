# Decisions

## 1.0.0

- One provider layer driven by data (`vendor/targets.json`), not a class per loader: every family differs only in template rewrites, pin reading and verification steps. Official templates stay the source of truth; the toolkit never reimplements loader build logic.
- Exact pins over ranges: Loom `1.19-SNAPSHOT` and ForgeGradle `[6.0,6.2)` / `[7.0.17,8)` are replaced at scaffold time by the newest matching release, recorded in the registry, so a project builds the same next month.
- Gradle's JDK per family: Loom 1.19 needs Java 25 whatever the mod targets; ForgeGradle 7 run tasks need a Java 8 toolchain. All local JDKs are offered as toolchains instead of enabling auto-download.
- Server-load evidence only from a log that shows the server started: NeoForge 1.21.1 exits 0 after refusing to start a zero-test server, so exit codes alone were a false pass.
- Java kits only where CI compiles them. 26.x targets get assets and data, and say plainly that Java is not generated, rather than shipping unverified code.
- Facts read from the game, not remembered: pack formats, folder names and recipe JSON shape come from each release's client JAR (range requests, nothing executed). Library metadata comes from each project's Modrinth record.
- Modrinth version ids in Gradle coordinates: version numbers are ambiguous across loaders and Minecraft versions (a real 1.20.1 build resolved a 1.21.4 file).
- `deploy` is the only write into a launcher instance: plan by default, `--apply` to write, receipt required, backups kept.

## 0.2.0

- Testable starters are opt-in (`init --with-tests`); existing callers and plain scaffolds are preserved.
- Keep providers, GameTests, metadata and empty structures in a separate `gameTest` source set and development mod, loaded only by datagen and the test server. The production JAR continues to use main output alone.
- Datagen selects only the provider's development mod ID; selecting two mod IDs introduces per-mod output folders and breaks the main resource layout. Generated recipes explicitly use the production namespace.
- Run datagen in its own invocation before tests/build so generated resources enter the runtime and final JAR. Validate XML testcase nodes and real recipe/JAR contents; task exit alone does not prove test coverage.
- Use a suffix-based development mod ID and enforce the58-character production ID limit only for this optional path. No new dependency, MCP or global configuration is needed.

## 0.1.0

- CLI + Python standard library, not a custom server: the required workflows are foreground file/build/API operations. No MCP/global provider configuration or standing schema cost is justified.
- NeoForge 1.21.1 first, matching installed reality. Newer 26.x lines have separate Java/API requirements. Fabric and Forge remain future providers, without placeholder abstractions now.
- Immutable official ModDevGradle MDK, not a reimplementation of loader build logic. Pinned commit, wrapper hash, Gradle distribution checksum and original template license are retained. Generated projects override NeoForge 21.1.264 to the installed 21.1.265.
- Reuse installed Python/JDK21. Disable silent JDK auto-download and persistent Gradle daemons in generated projects; optional explicit Temurin provisioning uses verified official metadata and hashes. The first Gradle run downloads its pinned toolchain inputs into local/gradle.
- Metadata declarations are inspection evidence, never a homegrown compatibility solver. Installed mods, configs, saves and launcher runtimes remain read-only. Inventory reports and the pack context stay local and are excluded from packages.
- Keep output focused: JAR source search and directory search cap matches at 50; full inventories are saved to files. Skill/agent references load by task phase. External APIs are optional, and publication remains a separate user action.
