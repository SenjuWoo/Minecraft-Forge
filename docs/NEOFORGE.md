# NeoForge 1.21.1 implementation routes

Use these routes to find evidence, then read the actual class or signature in the pinned dependency. Docs for 26.x, a later 1.21.x release, Forge or Fabric may describe different APIs.

## Workspace and source

The [1.21.1 getting-started guide](https://docs.neoforged.net/docs/1.21.1/gettingstarted/) requires a 64-bit Java 21 JDK. The official MDK supports Gradle-driven development and provides patched Minecraft/NeoForge sources after dependency setup. The toolkit uses ModDevGradle; its upstream [reference](https://github.com/neoforged/ModDevGradle) explains runs, source sets and dependency configurations.

The generated project's `gradle.properties`, `build.gradle`, wrapper properties and toolkit provenance file are its target lock. Do not upgrade one version independently because a search result says "latest". Use the wrapper instead of a separately installed Gradle.

## Registries and events

For new items/blocks, start with the MDK's example and [1.21.1 registries](https://docs.neoforged.net/docs/1.21.1/concepts/registries/). NeoForge recommends `DeferredRegister`; attach it to the mod event bus. Preserve registry IDs across upgrades because saved data depends on them.

Read the declaration of each event. The [events guide](https://docs.neoforged.net/docs/1.21.1/concepts/events/) distinguishes the game bus (`NeoForge.EVENT_BUS`) from the per-mod startup bus. Do not assume an event's bus from its name. For an interaction change, verify cancellation/result semantics and test that the effect happens once on the intended side.

## Resources and data generation

Inspect the [resource layout](https://docs.neoforged.net/docs/1.21.1/resources/) and a generated Minecraft example. Keep namespace, pluralization and model/recipe schemas specific to 1.21.1. Recipe examples and provider guidance live in [1.21.1 recipes](https://docs.neoforged.net/docs/1.21.1/resources/server/recipes/).

Check the MDK's data run and output directory before running `runData`. Add the relevant provider, run generation, inspect the resulting JSON and ensure the resources are packaged in the built JAR. A successful task with no provider does not show that recipes, tags or loot were generated.

## Sides and networking

Keep renderers, screens and other `net.minecraft.client` references behind client-only loading boundaries. A single-player run contains both logical sides, so it cannot establish dedicated-server compatibility. See [1.21.1 sides](https://docs.neoforged.net/docs/1.21.1/concepts/sides/).

Use the [1.21.1 payload API](https://docs.neoforged.net/docs/1.21.1/networking/payload/): register through `RegisterPayloadHandlersEvent`, use the target's payload types and codecs, and inspect handler threading. Bound data sizes; validate client requests on the server against permissions, distance, state and ownership before changing the world. Do not treat client-supplied values as authority.

For persistence, inspect the target's data components, attachments or saved-data API according to who owns the value and whether it must sync. Define save/load and migration behavior before changing existing stored formats.

## Integrations and invasive hooks

Declare exact game/loader ranges and required dependencies in `neoforge.mods.toml`. Put optional-mod references behind a safe optional loading boundary and test absent/present cases. Inventory output lists declarations, not a computed proof of compatibility.

Before an access transformer or mixin, check whether a public API or event already provides the hook. Verify the actual owner class, descriptor and target version from source or `javap`; keep the intervention narrow and test with the other mods that touch the same target. A successful transform is not proof of correct gameplay.

## Tests

Use ordinary Java tests for pure logic and [GameTests](https://docs.neoforged.net/docs/1.21.1/misc/gametest/) for world behavior. `runGameTestServer` being available does not mean the mod contains tests. Confirm the test namespace, actual test count, assertions and final result. See [TESTING.md](TESTING.md).

Sources checked 2026-10-27. Recheck the source for the pinned dependency whenever the target changes.
