"""`add`: one command per piece of content - assets, data and, where a kit exists, Java.

Everything is written into the owned project. Existing files are skipped unless
``force`` is set; language and tag files are merged. Java is generated only for
a loader/version this toolkit compiles in CI (see javagen.KITS); for any other
target the assets and data are still written and the result says what is left.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re

from . import __version__, javagen, pixelart, shapes
from .resources import facts, version_key
from .workbench import needs_load_test

KINDS = ("block", "item", "food", "sword", "pickaxe", "axe", "shovel", "hoe", "toolset", "armor", "mob", "furniture")
NAME = re.compile(r"[a-z][a-z0-9_]{1,47}")
ITEM_SHAPE = {"metal": "ingot", "gold": "ingot", "gem": "gemstone", "ruby": "gemstone", "arcane": "gemstone"}
MOB_COLOURS = {"stone": (0x6E6E76, 0xA4A4AC), "wood": (0x7C5432, 0xBE9060), "gem": (0x2296AA, 0xB0F8F4), "metal": (0x808C9E, 0xE6EEF6),
               "organic": (0x4C7E36, 0xA8D678), "arcane": (0x603896, 0xD29EF8), "ruby": (0xB02034, 0xFFAAB0), "gold": (0xD6A024, 0xFFF4AA),
               "bone": (0xC4BCA4, 0xFAF6E8), "flesh": (0xB06056, 0xF2BAA8), "leather": (0x704428, 0xBE865A)}


def _json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("_"))


class Writer:
    """Collects files for one `add`, then writes them with skip/merge rules."""

    def __init__(self, project: Path, mod_id: str, force: bool):
        self.project, self.mod_id, self.force = project, mod_id, force
        self.files: list[tuple[str, bytes]] = []
        self.lang: dict[str, str] = {}
        self.tags: dict[str, list[str]] = {}
        self.created: list[str] = []
        self.skipped: list[str] = []

    def asset(self, path: str, data: bytes):
        self.files.append((f"src/main/resources/assets/{self.mod_id}/{path}", data))

    def data(self, path: str, data: bytes, namespace: str | None = None, *, references: bool = False):
        # Data that names this mod's ids fails to parse while they are unregistered (fatal on 1.21+), so without
        # generated Java it waits in mcforge-pending/ until the content is registered.
        root = "mcforge-pending" if references and self.optional_tags else "src/main/resources"
        self.files.append((f"{root}/data/{namespace or self.mod_id}/{path}", data))

    def raw(self, path: str, data: bytes):
        self.files.append((path, data))

    optional_tags = False

    def tag(self, folder: str, tag: str, value: str):
        # Without generated Java the id is not registered yet; a required entry would break vanilla tags that include this one.
        entry = {"id": value, "required": False} if self.optional_tags else value
        self.tags.setdefault(f"src/main/resources/data/minecraft/{folder}/{tag}.json", []).append(entry)

    def flush(self):
        for relative, data in self.files:
            path = self.project / relative
            if path.exists() and not self.force:
                self.skipped.append(relative)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.created.append(relative)
        for relative, values in self.tags.items():
            path = self.project / relative
            current = {"replace": False, "values": []}
            if path.is_file():
                current = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(current, dict) or not isinstance(current.get("values"), list):
                    raise ValueError(f"Existing tag file is not a tag object: {relative}")
            ids = {value["id"] if isinstance(value, dict) else value for value in current["values"]}
            merged = current["values"] + [value for value in values if (value["id"] if isinstance(value, dict) else value) not in ids]
            if merged != current["values"] or not path.is_file():
                current["values"] = merged
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(_json(current))
                self.created.append(relative)
        if self.lang:
            relative = f"src/main/resources/assets/{self.mod_id}/lang/en_us.json"
            path = self.project / relative
            current = {}
            if path.is_file():
                current = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(current, dict):
                    raise ValueError("Existing language file must contain a JSON object")
            merged = current | {key: value for key, value in self.lang.items() if self.force or key not in current}
            if merged != current or not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(_json(merged))
                self.created.append(relative)


def _item_assets(writer: Writer, layout: dict, item: str, texture: bytes, parent: str = "minecraft:item/generated"):
    mod_id = writer.mod_id
    writer.asset(f"textures/item/{item}.png", texture)
    writer.asset(f"models/item/{item}.json", _json({"parent": parent, "textures": {"layer0": f"{mod_id}:item/{item}"}}))
    if layout["item_definitions"]:
        writer.asset(f"items/{item}.json", _json({"model": {"type": "minecraft:model", "model": f"{mod_id}:item/{item}"}}))
    writer.lang[f"item.{mod_id}.{item}"] = _title(item)


def _block_item_assets(writer: Writer, layout: dict, block: str, style: str):
    mod_id = writer.mod_id
    writer.asset(f"models/item/{block}.json", _json({"parent": f"{mod_id}:block/{block}"}))
    if layout["item_definitions"]:
        writer.asset(f"items/{block}.json", _json({"model": {"type": "minecraft:model", "model": f"{mod_id}:block/{block}"}}))
    writer.data(f"{layout['loot_table']}/blocks/{block}.json", references=True, data=_json({
        "type": "minecraft:block", "pools": [{"rolls": 1, "bonus_rolls": 0, "entries": [{"type": "minecraft:item", "name": f"{mod_id}:{block}"}],
                                             "conditions": [{"condition": "minecraft:survives_explosion"}]}]}))
    writer.tag(layout["block_tags"], "mineable/" + javagen.MINEABLE.get(style, "pickaxe"), f"{mod_id}:{block}")
    writer.lang[f"block.{mod_id}.{block}"] = _title(block)


def add_content(project: Path, kind: str, name: str, *, style: str = "auto", size: int = 16, tier: str = "iron",
                repair: str | None = None, shape: str | None = None, hostile: bool = False, force: bool = False,
                rig_override: tuple[dict, bytes] | None = None) -> dict:
    project = Path(project).resolve()
    if kind not in KINDS:
        raise ValueError("kind must be one of: " + ", ".join(KINDS))
    if not NAME.fullmatch(name):
        raise ValueError("name must match [a-z][a-z0-9_]{1,47}")
    if size not in (16, 32):
        raise ValueError("size must be 16 or 32 pixels")
    if tier not in javagen.TIERS:
        raise ValueError("tier must be one of: " + ", ".join(javagen.TIERS))
    if repair and not re.fullmatch(r"[a-z0-9_.-]+:[a-z0-9_./-]+", repair):
        raise ValueError("repair must be a namespaced item id such as minecraft:iron_ingot")
    lock_path = project / "mcforge-project.json"
    if not lock_path.is_file():
        raise ValueError(f"Not a Minecraft Forge project (missing {lock_path.name})")
    lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    mod_id, package = lock.get("mod_id"), lock.get("package")
    if not isinstance(mod_id, str) or not isinstance(package, str):
        raise ValueError("Project lock has no mod_id/package")
    from .project import project_family
    family = lock.get("family") or project_family(project)
    minecraft = lock["minecraft"]
    row = facts(minecraft)
    layout = row["layout"]
    kit = javagen.kit_for(family, minecraft)
    resolved = pixelart.resolve_style(style, name)
    if resolved not in pixelart.PALETTES:
        raise ValueError("style must be auto or one of: " + ", ".join(sorted(pixelart.PALETTES)))
    seed = pixelart.seed_of(mod_id, name, kind, resolved, str(size))
    writer = Writer(project, mod_id, force)
    writer.optional_tags = kit is None
    java: list[tuple[str, str, str]] = []     # (source set, class name relative to the content package, source)
    entrypoints: dict[str, list[str]] = {"main": [], "client": []}
    previews: list[dict] = []
    content_package = package + ".content"
    loader, era = kit if kit else (None, None)
    cls = javagen.pascal(name)
    regs: list[javagen.Registration] = []
    Reg = javagen.Registration

    def sprite(shape_name: str, sprite_seed: str) -> bytes:
        return pixelart.png_bytes(pixelart.sprite(shape_name, resolved, pixelart.seed_of(mod_id, sprite_seed, resolved), size))

    if kind == "block":
        writer.asset(f"blockstates/{name}.json", _json({"variants": {"": {"model": f"{mod_id}:block/{name}"}}}))
        writer.asset(f"models/block/{name}.json", _json({"parent": "minecraft:block/cube_all", "textures": {"all": f"{mod_id}:block/{name}"}}))
        writer.asset(f"textures/block/{name}.png", pixelart.png_bytes(pixelart.block_texture(seed, resolved, size)))
        _block_item_assets(writer, layout, name, resolved)
        regs = [Reg("BLOCK", "BLOCK", "Block", name, f"new Block({javagen.block_expression(resolved)})"),
                Reg("ITEM", "ITEM", "Item", name, "new BlockItem({REF:BLOCK}, new Item.Properties())", "BUILDING_BLOCKS")]
    elif kind in ("item", "food"):
        chosen = "food" if kind == "food" else shape or ITEM_SHAPE.get(resolved, "orb")
        if chosen not in pixelart.SPRITES:
            raise ValueError("item shape must be one of: " + ", ".join(sorted(pixelart.SPRITES)))
        _item_assets(writer, layout, name, sprite(chosen, name))
        expression = javagen.food_expression(era or "1.21") if kind == "food" else "new Item(new Item.Properties())"
        regs = [Reg("ITEM", "ITEM", "Item", name, expression, "FOOD_AND_DRINKS" if kind == "food" else "INGREDIENTS")]
    elif kind in ("sword", "pickaxe", "axe", "shovel", "hoe", "toolset"):
        tools = pixelart.TOOLS if kind == "toolset" else (kind,)
        tier_name = cls + "Tier"
        for tool in tools:
            item = f"{name}_{tool}" if kind == "toolset" else name
            _item_assets(writer, layout, item, sprite(tool, item), "minecraft:item/handheld")
            writer.tag(layout["item_tags"], tool + ("s" if not tool.endswith("s") else ""), f"{mod_id}:{item}")
            regs.append(Reg(tool.upper() if kind == "toolset" else "ITEM", "ITEM", "Item", item,
                            javagen.tool_expression(era or "1.21", tool, tier_name), javagen.TOOL_TAB.get(tool, "TOOLS_AND_UTILITIES")))
        if kit:
            java.append(("main", tier_name, javagen.tier_class(era, content_package, tier_name, tier, repair)))
        if kind == "toolset":
            cls += "Tools"
    elif kind == "armor":
        first, second = pixelart.armor_layers(resolved, seed)
        modern = layout["equipment"] is not None
        # Fabric on 1.20 resolves armor textures in the minecraft namespace; every other target uses the mod's own.
        vanilla_namespace = family == "fabric-loom" and not modern and version_key(minecraft) < (1, 20, 5)
        texture_name = f"{mod_id}_{name}" if vanilla_namespace else name
        if modern:
            writer.asset(f"textures/entity/equipment/humanoid/{name}.png", pixelart.png_bytes(first))
            writer.asset(f"textures/entity/equipment/humanoid_leggings/{name}.png", pixelart.png_bytes(second))
            writer.asset(f"{layout['equipment']}/{name}.json", _json({"layers": {
                "humanoid": [{"texture": f"{mod_id}:{name}"}], "humanoid_leggings": [{"texture": f"{mod_id}:{name}"}]}}))
        else:
            base = f"src/main/resources/assets/{'minecraft' if vanilla_namespace else mod_id}/textures/models/armor/{texture_name}"
            writer.raw(base + "_layer_1.png", pixelart.png_bytes(first))
            writer.raw(base + "_layer_2.png", pixelart.png_bytes(second))
        if era == "1.21":
            regs.append(Reg("MATERIAL", "ARMOR_MATERIAL", "ArmorMaterial", name, javagen.armor_material_expression(mod_id, name, tier, repair)))
        elif kit:
            material = cls + "ArmorMaterial"
            java.append(("main", material, javagen.armor_material_class(
                content_package, material, texture_name if vanilla_namespace else f"{mod_id}:{name}", tier, repair)))
        durability = javagen.TIERS[tier][6]
        slot_tags = {"helmet": "head_armor", "chestplate": "chest_armor", "leggings": "leg_armor", "boots": "foot_armor"}
        for piece in pixelart.ARMOR:
            item = f"{name}_{piece}"
            _item_assets(writer, layout, item, sprite(piece, item))
            writer.tag(layout["item_tags"], "trimmable_armor", f"{mod_id}:{item}")
            if version_key(minecraft) >= (1, 20, 5):
                writer.tag(layout["item_tags"], slot_tags[piece], f"{mod_id}:{item}")
            slot = f"ArmorItem.Type.{piece.upper()}"
            expression = (f"new ArmorItem({{HOLDER:MATERIAL}}, {slot}, new Item.Properties().durability({slot}.getDurability({durability})))"
                          if era == "1.21" else f"new ArmorItem({cls}ArmorMaterial.INSTANCE, {slot}, new Item.Properties())")
            regs.append(Reg(piece.upper(), "ITEM", "Item", item, expression, "COMBAT"))
        cls += "Armor"
    elif kind == "furniture":
        chosen = shape or next((key for key in shapes.FURNITURE if key in name), "chair")
        if chosen not in shapes.FURNITURE:
            raise ValueError("furniture shape must be one of: " + ", ".join(shapes.FURNITURE))
        texture = pixelart.png_bytes((pixelart.plank_texture if resolved in ("wood", "leather") else pixelart.block_texture)(seed, resolved, size))
        writer.asset(f"textures/block/{name}.png", texture)
        writer.asset(f"models/block/{name}.json", _json(shapes.furniture_model(mod_id, name, chosen)))
        writer.asset(f"blockstates/{name}.json", _json(shapes.furniture_blockstate(mod_id, name)))
        _block_item_assets(writer, layout, name, resolved)
        writer.raw(f"blockbench/{name}.bbmodel", _json(shapes.furniture_bbmodel(name, chosen, texture, size)))
        light = shapes.FURNITURE[chosen].get("light")
        block_class = cls + "Block"
        if kit:
            java.append(("main", block_class, javagen.furniture_class(era, content_package, block_class, shapes.furniture_shapes(chosen))))
        extra = ".noOcclusion()" + (f".lightLevel(state -> {light})" if light else "")
        regs = [Reg("BLOCK", "BLOCK", block_class, name, f"new {block_class}({javagen.block_expression(resolved, extra)})"),
                Reg("ITEM", "ITEM", "Item", name, "new BlockItem({REF:BLOCK}, new Item.Properties())", "FUNCTIONAL_BLOCKS")]
        previews.append({"kind": "block_model", "model": f"src/main/resources/assets/{mod_id}/models/block/{name}.json"})
    elif kind == "mob":
        if rig_override:
            rig, texture = rig_override
            image = pixelart.read_png(texture)
        else:
            archetype = shape or "quadruped"
            if archetype not in shapes.RIGS:
                raise ValueError("mob shape must be one of: " + ", ".join(shapes.RIGS))
            rig = shapes.mob_rig(archetype)
            image = pixelart.blank(*rig["texture"])
            rng = random.Random(seed)
            for part in rig["parts"]:
                for index, cube in enumerate(part["cubes"]):
                    pixelart.paint_box(image, *cube["uv"], cube["size"], pixelart.PALETTES[resolved], rng,
                                       face=("angry" if hostile else "calm") if part["face"] and index == 0 else None)
            texture = pixelart.png_bytes(image)
            writer.raw(f"blockbench/{name}.bbmodel", _json(shapes.rig_bbmodel(name, rig, texture)))
        writer.asset(f"textures/entity/{name}.png", texture)
        writer.data(f"{layout['loot_table']}/entities/{name}.json", _json({"type": "minecraft:entity", "pools": []}))
        writer.lang[f"entity.{mod_id}.{name}"] = _title(name)
        previews.append({"kind": "rig", "rig": rig, "image": image, "name": name})
        if kit:
            egg = f"{name}_spawn_egg"
            writer.asset(f"models/item/{egg}.json", _json({"parent": "minecraft:item/template_spawn_egg"}))
            writer.lang[f"item.{mod_id}.{egg}"] = _title(name) + " Spawn Egg"
            entity = cls + "Entity"
            width, height = rig["hitbox"]
            extra_imports = {entity: f"{content_package}.{entity}", cls + "Content": f"{content_package}.{cls}Content"}
            java.append(("main", entity, javagen.entity_class(content_package, entity, hostile, 24.0 if hostile else 12.0, 0.28 if hostile else 0.22, 3.0)))
            client_package = content_package + ".client"
            for suffix, source in (("Model", javagen.model_class(era, client_package, entity + "Model", entity, mod_id, name, rig, extra_imports)),
                                   ("Renderer", javagen.renderer_class(era, client_package, entity + "Renderer", entity, mod_id, name, rig["shadow"], extra_imports)),
                                   ("Client", None)):
                if source is None:
                    source = javagen.client_class(loader, client_package, entity + "Client", cls + "Content", entity, extra_imports)
                java.append(("client", "client." + entity + suffix, source))
            entrypoints["client"].append(f"{client_package}.{entity}Client")
            background, foreground = MOB_COLOURS[resolved]
            builder = (f'EntityType.Builder.of({entity}::new, MobCategory.{"MONSTER" if hostile else "CREATURE"})'
                       f'.sized({javagen.number(width)}, {javagen.number(height)}).clientTrackingRange(10).build("{name}")')
            regs = [Reg("TYPE", "ENTITY_TYPE", f"EntityType<{entity}>", name, builder),
                    Reg("SPAWN_EGG", "ITEM", "Item", egg, f"{{EGG:TYPE:0x{background:06X}:0x{foreground:06X}}}", "SPAWN_EGGS")]

    status = {"status": "not_generated", "reason": f"no Java kit for {family} on Minecraft {minecraft}; "
              "assets and data are written - register the content in Java yourself (guide content)", "classes": [],
              "pending": "after registering, move mcforge-pending/data/... into src/main/resources/data/... (loot tables name the new ids)"}
    if kit:
        attributes = ("TYPE", cls + "Entity") if kind == "mob" else None
        content_name = cls + "Content"
        java.insert(0, ("main", content_name, javagen.content_class(loader, era, content_package, mod_id, content_name, kind, regs, attributes=attributes)))
        entrypoints["main"].append(f"{content_package}.{content_name}")
        client_root = "src/client/java" if family == "fabric-loom" else "src/main/java"
        for source_set, relative, source in java:
            root = client_root if source_set == "client" else "src/main/java"
            writer.raw(f"{root}/{content_package.replace('.', '/')}/{relative.replace('.', '/')}.java", source.encode("utf-8"))
        status = {"status": "generated", "loader": loader, "era": era,
                  "classes": [f"{content_package}.{relative}" for _, relative, _ in java]}
    writer.flush()
    if kit and family == "fabric-loom":
        status["entrypoints"] = _fabric_entrypoints(project, entrypoints)
    rendered = []
    from . import preview
    for item in previews:
        output = project / "build/mcforge/previews" / f"{name}.png"
        if item["kind"] == "block_model":
            rendered.append(preview.preview_block_model(project, mod_id, project / item["model"], output)["preview"])
        else:
            rendered.append(preview.preview_rig(item["rig"], item["image"], output)["preview"])
    _record(project, kind, name, resolved, writer, status)
    result = {"project": str(project), "kind": kind, "name": name, "style": resolved, "minecraft": minecraft,
              "created": writer.created, "skipped": writer.skipped, "java": status, "previews": rendered,
              "next": ("verify PROJECT" if lock.get("with_tests") or lock.get("game_tests")
                       else "tests PROJECT, then verify PROJECT" if needs_load_test(lock)
                       else "verify PROJECT --load") if kit else "write the Java registration (guide content), then verify PROJECT"}
    if not row["exact"]:
        result["warning"] = f"No recorded facts for Minecraft {minecraft}; folder names follow {row['borrowed_from']}"
    return result


def _fabric_entrypoints(project: Path, entrypoints: dict[str, list[str]]) -> list[str]:
    """Add the generated initializers to fabric.mod.json; nothing else in the file changes."""
    path = project / "src/main/resources/fabric.mod.json"
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    added = []
    for side, classes in entrypoints.items():
        current = data.setdefault("entrypoints", {}).setdefault(side, [])
        for name in classes:
            if name not in current:
                current.append(name)
                added.append(f"{side}: {name}")
    if added:
        indent = "\t" if "\n\t" in text else 2
        path.write_text(json.dumps(data, indent=indent) + "\n", encoding="utf-8", newline="\n")
    return added


def _record(project: Path, kind: str, name: str, style: str, writer: Writer, status: dict):
    path = project / "mcforge-content.json"
    manifest = {"content": {}}
    if path.is_file():
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("content"), dict):
            raise ValueError("Existing content manifest must contain a JSON object")
    hashes = {relative: hashlib.sha256((project / relative).read_bytes()).hexdigest() for relative in writer.created}
    manifest["toolkit_version"] = __version__
    manifest["content"][f"{kind}:{name}"] = {"style": style, "java": status["status"], "files": hashes, "skipped": writer.skipped}
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _role(name: str) -> str | None:
    """Animation role from a bone name, matching the generated rigs' naming."""
    if "head" in name:
        return "head"
    if any(word in name for word in ("leg", "arm", "foot")):
        return "leg_a" if ("right" in name) != ("back" in name or "arm" in name) else "leg_b"
    return None


def import_bbmodel(project: Path, source: Path, *, block: str | None = None, entity: str | None = None, force: bool = False) -> dict:
    """Bring a Blockbench project into the mod: a block model, or an entity model class with its texture."""
    project = Path(project).resolve()
    if bool(block) == bool(entity):
        raise ValueError("Pass exactly one of --block ID or --entity ID")
    name = block or entity
    if not NAME.fullmatch(name):
        raise ValueError("id must match [a-z][a-z0-9_]{1,47}")
    source = Path(source)
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Blockbench project exceeds the 64 MiB inspection limit")
    parsed = shapes.read_bbmodel(json.loads(source.read_text(encoding="utf-8-sig")))
    lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8-sig"))
    mod_id, package = lock["mod_id"], lock["package"]
    if not parsed["textures"]:
        raise ValueError("The Blockbench project embeds no texture; in Blockbench, save the texture into the project first")
    texture = parsed["textures"][0]["png"]
    pixelart.read_png(texture)
    from . import preview
    if block:
        model = shapes.bbmodel_to_block_model(parsed, f"{mod_id}:block/{name}")
        writer = Writer(project, mod_id, True)
        layout = facts(lock["minecraft"])["layout"]
        writer.asset(f"textures/block/{name}.png", texture)
        writer.asset(f"models/block/{name}.json", _json(model))
        writer.flush()
        optional = Writer(project, mod_id, False)
        from .project import project_family
        optional.optional_tags = javagen.kit_for(lock.get("family") or project_family(project), lock["minecraft"]) is None
        optional.asset(f"blockstates/{name}.json", _json({"variants": {"": {"model": f"{mod_id}:block/{name}"}}}))
        _block_item_assets(optional, layout, name, "stone")
        optional.flush()
        rendered = preview.preview_block_model(project, mod_id, project / f"src/main/resources/assets/{mod_id}/models/block/{name}.json",
                                               project / "build/mcforge/previews" / f"{name}.png")
        return {"project": str(project), "block": name, "elements": len(model["elements"]), "created": writer.created + optional.created,
                "kept": optional.skipped, "preview": rendered["preview"],
                "next": "A block with this shape still needs a Block registered in Java (add furniture shows the pattern); then verify PROJECT"}
    rig = shapes.bbmodel_to_rig(parsed)
    for part in shapes.walk_parts(rig["parts"]):
        part["role"] = _role(part["name"])
    from .project import project_family
    family = lock.get("family") or project_family(project)
    kit = javagen.kit_for(family, lock["minecraft"])
    cls = javagen.pascal(name)
    content_package = package + ".content"
    root = "src/client/java" if family == "fabric-loom" else "src/main/java"
    model_path = project / root / content_package.replace(".", "/") / "client" / f"{cls}EntityModel.java"
    entity_path = project / "src/main/java" / content_package.replace(".", "/") / f"{cls}Entity.java"
    output = project / "build/mcforge/previews" / f"{name}.png"
    rendered = preview.preview_rig(rig, pixelart.read_png(texture), output)["preview"]
    if not kit:
        writer = Writer(project, mod_id, True)
        writer.asset(f"textures/entity/{name}.png", texture)
        writer.flush()
        return {"project": str(project), "entity": name, "bones": sum(1 for _ in shapes.walk_parts(rig["parts"])), "created": writer.created,
                "java": "not_generated", "preview": rendered,
                "next": f"No Java kit for {family} on Minecraft {lock['minecraft']}: export the model class from Blockbench or write it (guide content)"}
    if not entity_path.is_file():
        result = add_content(project, "mob", name, force=force, rig_override=(rig, texture))
        result["imported_from"] = str(source)
        return result
    manifest_path = project / "mcforge-content.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.is_file() else {"content": {}}
    relative = model_path.relative_to(project).as_posix()
    recorded = manifest.get("content", {}).get(f"mob:{name}", {}).get("files", {}).get(relative)
    if model_path.is_file() and not force and recorded != hashlib.sha256(model_path.read_bytes()).hexdigest():
        raise ValueError(f"{relative} was edited since it was generated; pass --force to replace it with the Blockbench model")
    extra = {cls + "Entity": f"{content_package}.{cls}Entity"}
    era = kit[1]
    source_text = javagen.model_class(era, content_package + ".client", cls + "EntityModel", cls + "Entity", mod_id, name, rig, extra)
    writer = Writer(project, mod_id, True)
    writer.raw(relative, source_text.encode("utf-8"))
    writer.asset(f"textures/entity/{name}.png", texture)
    writer.flush()
    entry = manifest.setdefault("content", {}).setdefault(f"mob:{name}", {"files": {}})
    for created in writer.created:
        entry.setdefault("files", {})[created] = hashlib.sha256((project / created).read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"project": str(project), "entity": name, "bones": sum(1 for _ in shapes.walk_parts(rig["parts"])), "created": writer.created,
            "java": "model class replaced", "preview": rendered, "next": "verify PROJECT --load"}
