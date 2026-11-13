# Minecraft Forge targets

Bundled: **forge-1.20.1** (Forge 47.4.28, Java 17, ForgeGradle 6.0.54) and **forge-26.3** (Forge 66.1.8, Java 25, ForgeGradle 7.0.40), from the official MDKs on maven.minecraftforge.net. The MDKs' version ranges for ForgeGradle are replaced by those exact releases. Forge 1.20.1 is still the largest modpack line; for 1.20.2+ most of the ecosystem moved to NeoForge.

```powershell
.\Minecraft-Forge.ps1 quickstart "D:\Mods\MyMod" --mod-id mymod --package dev.you.mymod --name "My Mod" --loader forge --minecraft 1.20.1
.\Minecraft-Forge.ps1 verify "D:\Mods\MyMod" --load
```

`--load` boots the headless game-test server after the build: it proves the mod constructs, registers and loads its data. Forge starts that server without any tests, so no extra wiring is needed.

## ForgeGradle 6 (1.20.1)

- Minecraft is obfuscated: dependencies on other mods go through `implementation fg.deobf("group:name:version")`. `libs --add` writes that form.
- Official Mojang names (`mapping_channel=official`). First setup decompiles Minecraft; it takes minutes and caches under the toolkit's `local/gradle`.
- Registration: `DeferredRegister` or `RegisterEvent` on the mod bus (`@Mod.EventBusSubscriber(bus = Bus.MOD)`); `add` uses `RegisterEvent` plus `RegistryObject.create(...)` handles so each generated class stands alone.
- Armor material: an `ArmorMaterial` implementation whose `getName()` is `"modid:name"`; Forge resolves `modid:textures/models/armor/name_layer_1.png`.

## ForgeGradle 7 (26.3)

- Minecraft is unobfuscated; plain `implementation` works for mod dependencies.
- The run tasks start ForgeGradle's Slime Launcher on a **Java 8** toolchain. The toolkit offers every local JDK to Gradle as a toolchain; if none is Java 8, `setup-java --major 8` installs one into the per-user JDK folder. Build and test tasks need only Java 25.
- Events moved to the EventBus 7 API (`FMLCommonSetupEvent.getBus(modBusGroup).addListener(...)`, `BuildCreativeModeTabContentsEvent.BUS`); read the MDK's `ExampleMod` and the exact sources before writing listeners. The toolkit has no 26.3 Java kit yet: `add` writes assets and data and says so.

## Sources

`sources --project PROJECT "Symbol"` searches the exact Forge sources JAR ForgeGradle prepared (`forge-<mc>-<version>-sources.jar`). On ForgeGradle 6 this JAR holds Forge's own classes; vanilla classes are decompiled into the IDE workspace, so use `javap` on the mapped Minecraft JAR or an IDE for those.

Sources: [Forge documentation](https://docs.minecraftforge.net/en/latest/), [ForgeGradle](https://github.com/MinecraftForge/ForgeGradle), [MDK downloads](https://files.minecraftforge.net/). Checked 2026-11-13.
