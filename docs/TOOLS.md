# Tools and dependency policy

## Included and resolved

| Component | Role | Provisioning |
|---|---|---|
| Minecraft Forge Python CLI and agent guides | Inspect, scaffold, run build workflows, find evidence | Included; Python standard library only |
| Official NeoForge MDK snapshot | Reproducible starting project | Bundled with immutable provenance and checksum |
| Gradle wrapper | Select the project build tool | In the MDK; downloads its pinned distribution on first use |
| Python 3.11+ | Run the CLI | Reuse the user's installed Python; `UABS_PYTHON` can select it |
| Java 21 JDK | Compile and run the 1.21.1 target | Discover/reuse a compatible installed JDK, including a complete launcher JDK |
| Minecraft, NeoForge and library artifacts | Build/runtime dependencies | Resolved by Gradle from the project's repositories and pins |
| `rg`, JDK `javap` | Find source and inspect exact signatures | Reuse installed CLIs; no MCP required |

This is a workbench, not a redistribution of Minecraft, the installed modpack, or every possible asset editor. First-use dependency downloads require internet. Inspect the CLI doctor and vendor manifest for exact bundled identities and locally resolved paths; do not infer a working tool from its directory name.

Use the correct JDK per target. A newer system JDK is not evidence that the 1.21.1 build is using Java 21. Avoid changing global PATH/JAVA_HOME, launcher runtimes or other agents' settings to make one project work.

If no compatible JDK exists, `Minecraft-Forge.ps1 setup-java --plan` resolves the official Windows x64 Temurin21 release, size and SHA-256. `setup-java` downloads and verifies it into the toolkit's `local/tools/jdk21`, preserving its notices and provenance. It never edits global Java settings. Other platforms can supply an official JDK21 through `MCFORGE_JAVA_HOME`.

## Source inspection

Resolve/decompile the target through ModDevGradle and use its prepared sources. Search narrowly by class, event or registry ID. `javap -classpath "<dependency.jar>" -p <qualified.ClassName>` can establish a compiled signature. Add `-c` when bytecode is necessary. `jar tf "<mod.jar>"` lists archive entries without executing the mod. Never execute a supplied mod merely to read metadata.

Prefer public API/source artifacts from the exact dependency version. Reading a mod JAR reveals its metadata and implementation; it does not grant permission to copy or redistribute its code/assets.

## External APIs

The CLI's `search` uses [Modrinth project search](https://docs.modrinth.com/api/operations/searchprojects/) with game and loader filters. Search results are candidates: read the selected project's license, exact version files, dependency declarations and side requirements before adding it. Modrinth requires an identifying User-Agent; observe response rate limits and avoid repeated broad searches. See its [API overview](https://docs.modrinth.com/api/).

For a download, record immutable project/version identity, original URL and the platform's published file hash; verify the bytes before use. Keep this in a project dependency manifest, not in a prompt. Do not scrape another project's private release or invent Gradle coordinates from its filename.

The [CurseForge API](https://docs.curseforge.com/rest-api/) uses an `x-api-key` and third-party access requirements. There is no bundled user key or automatic account setup. Some files restrict third-party distribution. Keep credentials in the caller's environment and honor the file's actual download permissions; never work around an absent download URL by guessing a CDN URL.

## Optional specialist tools

Use an existing image editor for textures, Blockbench for an appropriate model workflow, Blender for assets that need it, or an audio tool for sound. Resolve the installed tool and exact export format when that task arises. Do not preload editor bridges, cloud APIs or asset-generation services for ordinary Java work. A tool being available does not require using it.

No Minecraft MCP server is registered or running by default. The CLI supplies the current workflows without standing schemas or a background process. Add a project-scoped, on-demand MCP only if a future operation needs persistent editor/game state that the CLI cannot inspect efficiently.

## Tool failure

Read the exact error. Confirm runtime version, executable, permissions, network/repository access and wrapper pins before retrying. Repair the supported setup rather than downloading an unrelated toolchain or silently skipping a required check. Record the last successful command and the exact remaining gap in `STATE.md`.
