# Launchers and instances

ATLauncher is the reference launcher, and the toolkit reads the others the same way: **ATLauncher**, **Prism Launcher** (and PolyMC/MultiMC-format folders), **CurseForge**, **Modrinth App** and the **official launcher**'s `.minecraft`. Only instance metadata is read; accounts, tokens and launcher settings are never opened.

```powershell
.\Minecraft-Forge.ps1 instances                       # every launcher found in its default location
.\Minecraft-Forge.ps1 instances --launcher prism --root "E:\PrismLauncher"
.\Minecraft-Forge.ps1 inventory --instance "<instance folder>" --hash --output pack.json
.\Minecraft-Forge.ps1 deploy D:\Mods\MyMod --instance "<instance folder>"            # plan only
.\Minecraft-Forge.ps1 deploy D:\Mods\MyMod --instance "<instance folder>" --apply    # copy, with backup
```

| Launcher | Metadata read | Mods folder |
|---|---|---|
| ATLauncher | `instances/<name>/instance.json` | `<instance>/mods` |
| Prism / MultiMC | `instances/<name>/mmc-pack.json`, `instance.cfg` | `<instance>/.minecraft/mods` (or `minecraft/`) |
| CurseForge | `Instances/<name>/minecraftinstance.json` | `<instance>/mods` |
| Modrinth App | `profiles/<name>/profile.json` or the app's `app.db` (read-only) | `<profile>/mods` |
| Official | `.minecraft/launcher_profiles.json` | `.minecraft/mods` |

Each instance gets a `suggested_project`: the `init` options that build a mod for it, and whether that target is bundled or needs `--fetch`. A Quilt instance suggests Fabric; a vanilla instance suggests a data or resource pack (`pack`).

## Deploy

`deploy` is the only command that writes into an instance, and only with `--apply`.

1. It requires a fresh verification receipt (`verify PROJECT`) whose hashes still match the sources; `--unverified` uses the newest built JAR instead and says so.
2. It refuses an instance whose loader or Minecraft version differs from the project (`--allow-mismatch` overrides).
3. It checks the JAR's required dependencies against the instance (missing, or installed outside the declared range, counts as a mismatch) and lists them under `dependencies`.
4. `--apply` refuses while a game runs from that instance (Java process whose command line names its folder; `--allow-running` overrides): moving files under a running game left a pack half-changed.
5. It moves any JAR that provides the same mod id, and any file already at the destination name, into `<game dir>/mcforge-backups/<timestamp>/`, copies the new JAR and checks its hash. Nothing in `mods/` is overwritten.
6. It records the deploy in `<game dir>/mcforge-deployed.json`. `inventory` lists `deployed_missing`: mods deploy put there that no enabled JAR provides any more. A launcher reinstall or pack update can drop hand-added JARs without a word (seen: ten deployed mods gone after a pack update); redeploy them from each project's release JAR.

`inventory` also reports `dependency_problems` for the whole pack (required (Neo)Forge dependencies nobody provides; `nested?` = probably shipped inside another JAR) and `fml` for a JAR that FML loads through its manifest (`FMLModType`) or a loader service, so a multi-loader library with only `fabric.mod.json` is not called foreign.

Close the game first. Deploying is not a runtime test: launch the pack and read `logs/latest.log`. For a pack you care about, deploy into a copy of the instance first. Project folders are refused inside any launcher instance (`init`, `pack` and logs never write there).

Two launcher behaviours that bite automated pack work (seen on ATLauncher, 2026-11-24):

- The launcher rewrites `instance.json` from memory, so it can re-enable a mod you disabled on disk and can overwrite edits made while it runs. Close it before editing an instance; its own `disabledmods/` folder plus `"disabled": true` in `instance.json` is the supported way to turn a mod off.
- A running game keeps its JARs locked (Windows); moving or deleting `mods/` then fails halfway. Wait for the process to exit, and verify the mod set by hash afterwards.
