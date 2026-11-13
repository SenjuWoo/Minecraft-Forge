# Bundled and resolved components

The original toolkit code is MIT licensed. The official NeoForge MDK is an independent MIT-licensed template, copyright 2023 NeoForged project. Its `TEMPLATE_LICENSE.txt` is retained inside `vendor/neoforge-1.21.1-mdk.zip` and every generated project. Immutable source and SHA-256 are recorded in `vendor/manifest.json`.

The MDK includes the Gradle wrapper (Apache-2.0); its official wrapper script notices are retained. The pinned archive's authentic wrapper bytes match Gradle **8.14.3**'s published checksum (byte-identical through 8.14.5, which `vendor/manifest.json` records), while it launches the pinned **9.2.1** distribution. These versions need not match. Sources/checksums: [Gradle wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html), [8.14.3 wrapper checksum](https://services.gradle.org/distributions/gradle-8.14.3-wrapper.jar.sha256), [9.2.1 distribution checksum](https://services.gradle.org/distributions/gradle-9.2.1-bin.zip.sha256), [Gradle source license](https://github.com/gradle/gradle/blob/v9.2.1/LICENSE).

Downloaded Gradle distributions, NeoForge, Minecraft, Mojang mappings, Parchment and libraries retain their respective licenses. They are resolved by the project and are not included in the portable toolkit. Read mapping license terms in the actual mapping artifact; upstream reference: [NeoForm Mojang mapping notice](https://github.com/NeoForged/NeoForm/blob/main/Mojang.md).

Optional `setup-java` uses the [official Adoptium API](https://api.adoptium.net/) and official Temurin21 GitHub releases. It resolves an immutable release URL, verifies the published SHA-256 and retains that JDK's license/notices. Java is not included in the portable toolkit. Installed mods are inspected locally and never bundled by the toolkit package command.

## Templates added in 1.0.0

Recorded with source URL, commit or version and SHA-256 in `vendor/targets.json` (refresh: `scripts/vendor_templates.py`).

- NeoForge 26.3 MDK: MIT, copyright 2023 NeoForged project; `TEMPLATE_LICENSE.txt` retained in the archive and generated projects.
- Fabric example mod (branches 1.20.1, 1.21.1, 26.3): CC0-1.0 dedication by FabricMC. Generated projects drop the template's CC0 `LICENSE` and mark `fabric.mod.json` as `All-Rights-Reserved` so the author chooses the mod's own licence.
- Minecraft Forge MDKs 1.20.1-47.4.28 and 26.3-66.1.8: Forge's `LICENSE.txt` (LGPL-2.1 with its stated exceptions for mods) is retained in the archives and generated projects.
- Each template's Gradle wrapper (Apache-2.0) matches a published Gradle wrapper checksum; distributions are pinned by their published SHA-256.

`mcforge/data/minecraft_versions.json` holds facts (pack formats, folder names, recipe shape) read from Mojang's client JARs; no game files are included. `mcforge/data/libraries.json` holds titles, licences, links and version ranges from the Modrinth API. Libraries added with `libs` are resolved by Gradle from Modrinth's Maven and keep their own licences.
