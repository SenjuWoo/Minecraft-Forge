# Decisions

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
