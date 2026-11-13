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
3. It moves any JAR that provides the same mod id into `<game dir>/mcforge-backups/<timestamp>/`, copies the new JAR and checks its hash.

Close the game first. Deploying is not a runtime test: launch the pack and read `logs/latest.log`. For a pack you care about, deploy into a copy of the instance first. Project folders are refused inside any launcher instance (`init`, `pack` and logs never write there).
