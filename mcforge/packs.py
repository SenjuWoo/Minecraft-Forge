"""Packs that need no compiled mod: resource packs, data packs and shader packs.

Resource and data packs take their pack format from the facts read out of the
game (resources.py). A resource pack can carry procedural retextures of any
vanilla texture path; a data pack starts with a working function, tag and
recipe; a shader pack is a small post-processing pack for Iris / OptiFine.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import zipfile

from . import pixelart
from .resources import facts, pack_mcmeta

TEXTURE = re.compile(r"(?:minecraft:)?((?:block|item|entity)/[a-z0-9_/]+)")
FUNCTION_ID = re.compile(r"[a-z0-9_]{1,40}")


def _write(root: Path, relative: str, data: bytes | str):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _json(value) -> str:
    return json.dumps(value, indent=2) + "\n"


SHADER_VERTEX = """#version 120
// Full-screen pass: Iris and OptiFine draw one quad covering the screen.
varying vec2 texcoord;

void main() {
    gl_Position = ftransform();
    texcoord = gl_MultiTexCoord0.st;
}
"""
SHADER_FINAL = """#version 120
// Post-processing on the finished frame. Options are declared in shaders.properties.
uniform sampler2D colortex0;
uniform float viewWidth;
uniform float viewHeight;
varying vec2 texcoord;

#define SATURATION 1.15 // [0.8 1.0 1.15 1.3 1.5]
#define VIGNETTE 0.35 // [0.0 0.2 0.35 0.5]
#define WARMTH 0.04 // [0.0 0.02 0.04 0.08]

void main() {
    vec3 colour = texture2D(colortex0, texcoord).rgb;
    float grey = dot(colour, vec3(0.2126, 0.7152, 0.0722));
    colour = mix(vec3(grey), colour, SATURATION);
    colour += vec3(WARMTH, WARMTH * 0.4, -WARMTH);
    vec2 centred = texcoord - 0.5;
    centred.x *= viewWidth / max(viewHeight, 1.0);
    colour *= 1.0 - VIGNETTE * smoothstep(0.35, 0.95, length(centred));
    gl_FragColor = vec4(clamp(colour, 0.0, 1.0), 1.0);
}
"""


def create_pack(destination: Path, kind: str, name: str, minecraft: str, *, retexture: list[str] | None = None,
                style: str = "auto", size: int = 16, archive: bool = False) -> dict:
    destination = Path(os.path.abspath(destination))
    from .workbench import guard_output
    guard_output(destination)
    if kind not in ("resource", "data", "shader"):
        raise ValueError("pack kind must be resource, data or shader")
    if destination.exists():
        raise ValueError("Destination must not exist; existing files are never overwritten")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must already exist")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}", name):
        raise ValueError("name must be 1-80 plain letters, numbers, spaces, underscores, dots or hyphens")
    row = facts(minecraft)
    created = []
    namespace = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_") or "pack"
    if kind == "shader":
        files = {"shaders/final.vsh": SHADER_VERTEX, "shaders/final.fsh": SHADER_FINAL,
                 "shaders/shaders.properties": "# Options shown in the shader settings screen.\nscreen=SATURATION VIGNETTE WARMTH\n",
                 "shaders/lang/en_us.lang": "option.SATURATION=Saturation\noption.VIGNETTE=Vignette\noption.WARMTH=Warmth\n",
                 "README.md": f"# {name}\n\nPost-processing shader pack for Iris or OptiFine. Install: copy this folder or its ZIP into "
                              "`shaderpacks/`, then pick it under Video Settings > Shader Packs.\n\nNot runtime-tested by the toolkit: "
                              "load it in a client and check the log for GLSL compile errors.\n"}
    else:
        files = {"pack.mcmeta": _json(pack_mcmeta(minecraft, kind, f"{name} ({minecraft})"))}
        if kind == "resource":
            files["README.md"] = (f"# {name}\n\nResource pack for Minecraft {minecraft}. Install: copy into `resourcepacks/`. "
                                  "Textures replace vanilla ones at the same path under assets/minecraft/textures.\n")
            for reference in retexture or []:
                match = TEXTURE.fullmatch(reference)
                if not match:
                    raise ValueError(f"--retexture takes vanilla texture paths like block/stone or item/diamond_sword, got {reference!r}")
                path = match[1]
                resolved = pixelart.resolve_style(style, path.rsplit("/", 1)[-1])
                seed = pixelart.seed_of(name, path, resolved, str(size))
                shape = next((tool for tool in pixelart.TOOLS + pixelart.ARMOR if path.endswith("_" + tool)), None)
                image = (pixelart.sprite(shape, resolved, seed, size) if path.startswith("item/") and shape
                         else pixelart.sprite("orb", resolved, seed, size) if path.startswith("item/")
                         else pixelart.block_texture(seed, resolved, size))
                files[f"assets/minecraft/textures/{path}.png"] = pixelart.png_bytes(image)
        else:
            layout = row["layout"]
            function_dir = "function" if layout["loot_table"] == "loot_table" else "functions"
            tag_dir = "tags/" + ("function" if function_dir == "function" else "functions")
            # Recipe JSON shape is read from the game's own flint_and_steel recipe (scripts/build_facts.py).
            ingredient = (lambda item: item) if layout["recipe_ingredient"] == "string" else (lambda item: {"item": item})
            recipe = {"type": "minecraft:crafting_shapeless", "ingredients": [ingredient("minecraft:dirt"), ingredient("minecraft:wheat_seeds")],
                      "result": {layout["recipe_result_key"]: "minecraft:grass_block", "count": 1}}
            files.update({
                f"data/{namespace}/{function_dir}/hello.mcfunction": f'tellraw @a {{"text":"{name} loaded","color":"green"}}\n',
                f"data/minecraft/{tag_dir}/load.json": _json({"values": [f"{namespace}:hello"]}),
                f"data/{namespace}/{layout['recipe']}/grass_from_dirt.json": _json(recipe),
                "README.md": (f"# {name}\n\nData pack for Minecraft {minecraft}. Install: copy into `saves/WORLD/datapacks/` "
                              "(or a modpack's global datapack folder), then run /reload. On load it prints a line in chat and adds "
                              "a shapeless recipe: dirt + wheat seeds -> grass block.\n"),
            })
    for relative, data in files.items():
        _write(destination, relative, data)
        created.append(relative)
    result = {"pack": str(destination), "kind": kind, "minecraft": minecraft, "files": sorted(created)}
    if kind != "shader":
        result["pack_format"] = json.loads(files["pack.mcmeta"])["pack"]
        if not row["exact"]:
            result["warning"] = f"No recorded facts for {minecraft}; format follows {row['borrowed_from']}"
    if archive:
        output = destination.with_suffix(".zip")
        guard_output(output)
        if output.exists():
            raise ValueError(f"{output} exists; remove it or skip --zip")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
            for relative in sorted(created):
                bundle.write(destination / relative, relative)
        result["zip"] = str(output)
    return result
