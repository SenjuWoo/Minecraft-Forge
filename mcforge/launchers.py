"""Find launcher instances read-only, and deploy a built mod only on explicit request.

ATLauncher is the reference launcher; Prism/MultiMC-family, CurseForge, the
Modrinth App and the official launcher are read through their own instance
metadata. Accounts, tokens and launcher settings are never opened. ``deploy``
is the one command that writes into an instance, and only with ``--apply``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

from .inventory import MAX_INSTANCE_BYTES, _bounded_read, inspect_jar

LAUNCHERS = ("atlauncher", "prism", "curseforge", "modrinth", "vanilla")
LOADER_NAMES = {"neoforge": "NeoForge", "forge": "Forge", "fabric": "Fabric", "quilt": "Quilt"}
PRISM_COMPONENTS = {"net.neoforged": "NeoForge", "net.minecraftforge": "Forge", "net.fabricmc.fabric-loader": "Fabric",
                    "org.quiltmc.quilt-loader": "Quilt"}


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def default_roots() -> dict[str, list[Path]]:
    """Conventional install locations per launcher; a missing folder just yields nothing."""
    appdata = Path(os.environ.get("APPDATA", _home("AppData/Roaming")))
    return {
        "atlauncher": [appdata / "ATLauncher", _home(".local/share/atlauncher"), _home("Library/Application Support/ATLauncher")],
        "prism": [appdata / "PrismLauncher", _home(".local/share/PrismLauncher"), _home("Library/Application Support/PrismLauncher"),
                  _home(".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher"), appdata / "PolyMC", _home(".local/share/PolyMC"),
                  _home(".local/share/multimc")],
        "curseforge": [_home("curseforge/minecraft"), _home("Documents/curseforge/minecraft")],
        "modrinth": [appdata / "ModrinthApp", appdata / "com.modrinth.theseus", _home(".local/share/ModrinthApp"),
                     _home("Library/Application Support/ModrinthApp")],
        "vanilla": [appdata / ".minecraft", _home(".minecraft"), _home("Library/Application Support/minecraft")],
    }


def _blank(launcher: str, path: Path) -> dict:
    return {"launcher": launcher, "path": str(path), "name": path.name, "minecraft": None, "loader": {"type": None, "version": None},
            "java_major": None, "game_dir": str(path), "errors": []}


def _json(path: Path):
    return json.loads(_bounded_read(path, MAX_INSTANCE_BYTES))


def game_dir(instance: Path) -> Path:
    """Folder holding mods/ and saves/: the instance itself, or its .minecraft / minecraft child."""
    for candidate in (instance, instance / ".minecraft", instance / "minecraft"):
        if (candidate / "mods").is_dir():
            return candidate
    for candidate in (instance / ".minecraft", instance / "minecraft"):
        if candidate.is_dir():
            return candidate
    return instance


def describe(instance: Path) -> dict:
    """Summarise one instance from whichever launcher's metadata file it carries."""
    instance = Path(instance)
    try:
        if (instance / "instance.json").is_file():
            result = _blank("atlauncher", instance)
            data = _json(instance / "instance.json")
            launcher = data.get("launcher", {})
            loader = launcher.get("loaderVersion") or {}
            result.update(name=launcher.get("name", instance.name), minecraft=launcher.get("version") or data.get("id"),
                          loader={"type": loader.get("type"), "version": loader.get("version")},
                          java_major=(data.get("javaVersion") or {}).get("majorVersion"))
        elif (instance / "mmc-pack.json").is_file():
            result = _blank("prism", instance)
            for component in _json(instance / "mmc-pack.json").get("components", []):
                uid, version = component.get("uid"), component.get("version")
                if uid == "net.minecraft":
                    result["minecraft"] = version
                elif uid in PRISM_COMPONENTS:
                    result["loader"] = {"type": PRISM_COMPONENTS[uid], "version": version}
            config = instance / "instance.cfg"
            if config.is_file():
                match = re.search(r"(?m)^name=(.+)$", _bounded_read(config, 1 << 20).decode("utf-8", "replace"))
                if match:
                    result["name"] = match[1].strip()
        elif (instance / "minecraftinstance.json").is_file():
            result = _blank("curseforge", instance)
            data = _json(instance / "minecraftinstance.json")
            result.update(name=data.get("name", instance.name), minecraft=data.get("gameVersion"))
            base = (data.get("baseModLoader") or {}).get("name", "")
            match = re.fullmatch(r"(neoforge|forge|fabric|quilt)-([0-9][0-9A-Za-z.+-]*?)(?:-\d+(?:\.\d+)+)?", base)
            if match:
                result["loader"] = {"type": LOADER_NAMES[match[1]], "version": match[2]}
        elif (instance / "profile.json").is_file():
            result = _blank("modrinth", instance)
            metadata = _json(instance / "profile.json").get("metadata", {})
            loader = metadata.get("loader")
            result.update(name=metadata.get("name", instance.name), minecraft=metadata.get("game_version"),
                          loader={"type": LOADER_NAMES.get(loader, loader) if loader and loader != "vanilla" else None,
                                  "version": (metadata.get("loader_version") or {}).get("id")})
        else:
            result = _blank("unknown", instance)
            result["errors"].append("no recognised launcher metadata; loader and version are unknown")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result = _blank("unknown", instance)
        result["errors"].append(f"instance metadata: {error}")
    result["game_dir"] = str(game_dir(instance))
    return result


def _modrinth_database(root: Path) -> dict[str, dict]:
    """Newer Modrinth App builds keep profile metadata in app.db; read it without locking or writing."""
    database = root / "app.db"
    if not database.is_file():
        return {}
    try:
        import sqlite3
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro&immutable=1", uri=True, timeout=1)
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(profiles)")}
            wanted = [name for name in ("path", "name", "game_version", "mod_loader", "mod_loader_version") if name in columns]
            if "path" not in wanted:
                return {}
            return {row[0]: dict(zip(wanted, row)) for row in connection.execute(f"SELECT {', '.join(wanted)} FROM profiles")}
        finally:
            connection.close()
    except Exception:  # an unreadable or reshaped database only loses metadata, never the listing
        return {}


def _vanilla(root: Path) -> list[dict]:
    result = _blank("vanilla", root)
    result["name"] = "Official launcher (.minecraft)"
    try:
        profiles = _json(root / "launcher_profiles.json").get("profiles", {})
        ids = sorted({profile.get("lastVersionId", "") for profile in profiles.values() if isinstance(profile, dict)})
        found = []
        for version in ids:
            for pattern, loader in ((r"(?P<mc>\d+(?:\.\d+)+)-forge-(?P<v>[\d.]+)", "Forge"), (r"neoforge-(?P<v>[\d.]+(?:-beta)?)", "NeoForge"),
                                    (r"fabric-loader-(?P<v>[\d.]+)-(?P<mc>\d+(?:\.\d+)+)", "Fabric"),
                                    (r"quilt-loader-(?P<v>[\d.a-z-]+)-(?P<mc>\d+(?:\.\d+)+)", "Quilt")):
                match = re.fullmatch(pattern, version)
                if match:
                    found.append({"type": loader, "version": match["v"], "minecraft": match.groupdict().get("mc")})
        result["profiles"] = found
        if len(found) == 1:
            result.update(minecraft=found[0]["minecraft"], loader={"type": found[0]["type"], "version": found[0]["version"]})
        elif found:
            result["errors"].append("several modded profiles share this game folder; pass the loader and version yourself")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result["errors"].append(f"launcher_profiles.json: {error}")
    return [result]


def discover(launcher: str = "all", roots: list[Path] | None = None) -> list[dict]:
    """List instances of one launcher or all of them, each with a suggested project target."""
    if launcher != "all" and launcher not in LAUNCHERS:
        raise ValueError("launcher must be all or one of: " + ", ".join(LAUNCHERS))
    found: list[dict] = []
    seen: set[str] = set()
    for name, defaults in default_roots().items():
        if launcher not in ("all", name):
            continue
        for root in (roots if roots is not None else defaults):
            root = Path(root)
            if not root.is_dir():
                continue
            if name == "vanilla":
                rows = _vanilla(root) if (root / "launcher_profiles.json").is_file() else []
            else:
                folder = {"atlauncher": "instances", "prism": "instances", "curseforge": "Instances", "modrinth": "profiles"}[name]
                directory = root / folder
                marker = {"atlauncher": "instance.json", "prism": "mmc-pack.json", "curseforge": "minecraftinstance.json"}.get(name)
                children = sorted(path for path in directory.iterdir() if path.is_dir()) if directory.is_dir() else []
                rows = [describe(path) for path in children if marker is None or (path / marker).is_file()]
                if name == "modrinth":
                    database = _modrinth_database(root)
                    for row in rows:
                        row["launcher"] = "modrinth"
                        extra = database.get(Path(row["path"]).name)
                        if extra and not row["minecraft"]:
                            loader = extra.get("mod_loader")
                            row.update(name=extra.get("name") or row["name"], minecraft=extra.get("game_version"), errors=[],
                                       loader={"type": LOADER_NAMES.get(loader, loader) if loader and loader != "vanilla" else None,
                                               "version": extra.get("mod_loader_version")})
            for row in rows:
                key = os.path.normcase(row["path"])
                if key not in seen:
                    seen.add(key)
                    row["suggested_project"] = suggest(row)
                    found.append(row)
    return found


def suggest(instance: dict) -> dict:
    """Which `init` options build a mod for this instance, and whether that target is bundled."""
    loader = (instance["loader"].get("type") or "").lower()
    minecraft = instance.get("minecraft")
    if not minecraft:
        return {"status": "unknown", "note": "instance does not state its Minecraft version"}
    if loader == "quilt":
        loader, note = "fabric", "Quilt loads Fabric mods; build against Fabric"
    elif loader not in ("neoforge", "forge", "fabric"):
        return {"status": "no_loader", "note": "vanilla instance: a mod needs a loader; a data or resource pack does not (pack command)"}
    else:
        note = None
    from .targets import load_targets
    bundled = [name for name, target in load_targets()["targets"].items() if target["loader"] == loader and target["minecraft"] == minecraft]
    options = f"--loader {loader} --minecraft {minecraft}"
    version = instance["loader"].get("version")
    if version and instance["loader"]["type"] in ("NeoForge", "Forge"):
        options += f" --loader-version {version}"
    result = {"status": "bundled" if bundled else "on_demand", "init_options": options if bundled else options + " --fetch"}
    if note:
        result["note"] = note
    if not bundled:
        result["note"] = ((note + "; ") if note else "") + "not a bundled target: --fetch resolves the official template, which this toolkit release did not build"
    return result


def deploy(project: Path, instance: Path, *, apply: bool = False, allow_mismatch: bool = False, unverified: bool = False) -> dict:
    """Plan, or with ``apply`` perform, copying the verified mod JAR into an instance's mods folder."""
    project, instance = Path(project).resolve(), Path(instance).resolve()
    lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8-sig"))
    mod_id = lock["mod_id"]
    if unverified:
        candidates = sorted((project / "build/libs").glob(f"{mod_id}-*.jar"), key=lambda path: path.stat().st_mtime_ns)
        candidates = [path for path in candidates if not path.name.endswith(("-sources.jar", "-dev.jar", "-slim.jar"))]
        if not candidates:
            raise ValueError("No built JAR in build/libs; run verify PROJECT first")
        artifact, evidence = candidates[-1], "unverified: newest JAR in build/libs, no receipt checked"
    else:
        from .verification import check_receipt
        receipt = check_receipt(project)
        artifact, evidence = Path(receipt["artifact"]["path"]), f"receipt {receipt['run_id']} matches the current sources"
    summary = describe(instance)
    mods = Path(summary["game_dir"]) / "mods"
    if not mods.is_dir():
        raise ValueError(f"Instance has no mods folder: {mods}")
    project_loader = lock.get("loader", "neoforge")
    instance_loader = (summary["loader"].get("type") or "").lower()
    mismatch = []
    if instance_loader and instance_loader != project_loader and not (instance_loader == "quilt" and project_loader == "fabric"):
        mismatch.append(f"instance loader {summary['loader']['type']} != project loader {project_loader}")
    if summary["minecraft"] and summary["minecraft"] != lock["minecraft"]:
        mismatch.append(f"instance Minecraft {summary['minecraft']} != project Minecraft {lock['minecraft']}")
    if mismatch and not allow_mismatch:
        raise ValueError("Instance does not match the project: " + "; ".join(mismatch) + ". Pass --allow-mismatch to deploy anyway")
    replaced = [path for path in sorted(mods.glob("*.jar"))
                if any(mod["mod_id"] == mod_id for mod in inspect_jar(path)["mods"])]
    destination = mods / artifact.name
    backup = Path(summary["game_dir"]) / "mcforge-backups" / time.strftime("%Y%m%d-%H%M%S")
    plan = {"project": str(project), "instance": summary["name"], "launcher": summary["launcher"], "artifact": str(artifact),
            "evidence": evidence, "destination": str(destination), "replaces": [str(path) for path in replaced],
            "backup": str(backup) if replaced else None, "mismatch": mismatch, "applied": False,
            "note": "Close the game first. The mod loads on the next launch; this is not a runtime test."}
    if not apply:
        plan["next"] = "Review the plan, then repeat with --apply"
        return plan
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if replaced:
        backup.mkdir(parents=True)
        for path in replaced:
            shutil.move(str(path), str(backup / path.name))
    shutil.copy2(artifact, destination)
    with destination.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError("Deployed JAR differs from the built artifact; restore from the backup folder")
    plan.update(applied=True, sha256=digest)
    return plan
