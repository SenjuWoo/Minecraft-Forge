"""Deterministic pixel art with the standard library only.

Images are lists of RGBA ``bytearray`` rows. Sprites are drawn as coarse masks
and then outlined and shaded by one rule, so every generated icon shares the
same light direction and outline weight. Nothing is downloaded or copied.
"""
from __future__ import annotations

import hashlib
import random
import struct
import zlib

Image = list[bytearray]

# shadow, base, light, highlight
PALETTES = {
    "stone": ((74, 74, 80), (104, 104, 110), (134, 134, 140), (164, 164, 170)),
    "wood": ((88, 58, 36), (124, 84, 50), (158, 112, 68), (190, 144, 96)),
    "gem": ((20, 92, 112), (34, 150, 170), (72, 210, 218), (176, 248, 244)),
    "metal": ((86, 96, 112), (128, 140, 158), (178, 190, 204), (230, 238, 246)),
    "organic": ((48, 88, 40), (76, 126, 54), (112, 170, 78), (168, 214, 120)),
    "arcane": ((60, 34, 100), (96, 56, 150), (142, 88, 204), (210, 158, 248)),
    "ruby": ((110, 18, 34), (176, 32, 52), (226, 70, 88), (255, 170, 176)),
    "gold": ((150, 98, 16), (214, 160, 36), (248, 208, 72), (255, 244, 170)),
    "bone": ((150, 142, 120), (196, 188, 164), (226, 220, 200), (250, 246, 232)),
    "flesh": ((120, 60, 56), (176, 96, 86), (214, 138, 122), (242, 186, 168)),
    "leather": ((74, 44, 26), (112, 68, 40), (150, 96, 58), (190, 134, 90)),
}
HANDLE = ((40, 30, 11), (73, 54, 21), (104, 78, 30), (137, 103, 39))
STYLE_WORDS = (
    ("ruby", ("ruby", "garnet", "crimson", "blood")),
    ("gold", ("gold", "amber", "brass", "honey")),
    ("wood", ("wood", "log", "plank", "bark", "beam", "oak", "birch", "spruce", "chair", "table", "stool", "bench", "shelf", "cabinet")),
    ("gem", ("gem", "diamond", "emerald", "crystal", "shard", "amethyst", "sapphire", "aqua")),
    ("metal", ("iron", "steel", "copper", "metal", "ingot", "silver", "bronze", "tin", "lamp")),
    ("organic", ("leaf", "grass", "seed", "food", "plant", "moss", "berry", "slime", "frog")),
    ("arcane", ("rune", "arcane", "magic", "ender", "soul", "void", "spirit", "wraith")),
    ("bone", ("bone", "skull", "skeleton", "ivory")),
    ("flesh", ("flesh", "meat", "pig", "boar", "zombie")),
    ("leather", ("leather", "hide", "fur", "bear", "wolf")),
)


def clamp(value: float) -> int:
    return 0 if value < 0 else 255 if value > 255 else int(value)


def seed_of(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(":".join(parts).encode("utf-8")).digest()[:8], "big")


def resolve_style(style: str, asset_id: str) -> str:
    """Resolve ``auto`` from words in the asset id; an explicit style is never changed."""
    if style != "auto":
        return style
    value = asset_id.lower()
    for name, words in STYLE_WORDS:
        if any(word in value for word in words):
            return name
    return "stone"


def blank(width: int, height: int) -> Image:
    return [bytearray(width * 4) for _ in range(height)]


def put(image: Image, x: int, y: int, colour, alpha: int = 255):
    if 0 <= y < len(image) and 0 <= x < len(image[0]) // 4:
        image[y][x * 4:x * 4 + 4] = bytes((clamp(colour[0]), clamp(colour[1]), clamp(colour[2]), alpha))


def get(image: Image, x: int, y: int) -> tuple[int, int, int, int]:
    return tuple(image[y][x * 4:x * 4 + 4])


def scale(image: Image, factor: int) -> Image:
    if factor == 1:
        return image
    rows = []
    for row in image:
        wide = bytearray()
        for x in range(len(row) // 4):
            wide += row[x * 4:x * 4 + 4] * factor
        rows.extend(bytearray(wide) for _ in range(factor))
    return rows


def png_bytes(image: Image) -> bytes:
    """Write an RGBA PNG without Pillow or any external process."""
    width, height = len(image[0]) // 4, len(image)
    raw = b"".join(b"\x00" + bytes(row) for row in image)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def read_png(data: bytes) -> Image:
    """Decode a non-interlaced 8-bit PNG (grey, RGB, palette, with or without alpha) to RGBA rows."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")
    position, chunks, palette, transparency = 8, [], None, None
    header = None
    while position + 8 <= len(data):
        length, tag = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            palette = body
        elif tag == b"tRNS":
            transparency = body
        elif tag == b"IDAT":
            chunks.append(body)
        elif tag == b"IEND":
            break
    if not header:
        raise ValueError("PNG has no header")
    width, height, depth, colour, _, _, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if depth != 8 or interlace or channels is None or width * height > 4096 * 4096:
        raise ValueError("Unsupported PNG: need 8-bit, non-interlaced, at most 4096x4096")
    raw = zlib.decompress(b"".join(chunks))
    stride = width * channels
    previous = bytearray(stride)
    image: Image = []
    offset = 0
    for _ in range(height):
        kind = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            corner = previous[index - channels] if index >= channels else 0
            if kind == 1:
                line[index] = (line[index] + left) & 255
            elif kind == 2:
                line[index] = (line[index] + up) & 255
            elif kind == 3:
                line[index] = (line[index] + (left + up) // 2) & 255
            elif kind == 4:
                estimate = left + up - corner
                a, b, c = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                line[index] = (line[index] + (left if a <= b and a <= c else up if b <= c else corner)) & 255
        previous = line
        row = bytearray()
        for x in range(width):
            pixel = line[x * channels:(x + 1) * channels]
            if colour == 6:
                row += pixel
            elif colour == 2:
                row += pixel + b"\xff"
            elif colour == 0:
                row += bytes((pixel[0], pixel[0], pixel[0], 255))
            elif colour == 4:
                row += bytes((pixel[0], pixel[0], pixel[0], pixel[1]))
            else:
                index = pixel[0]
                alpha = transparency[index] if transparency and index < len(transparency) else 255
                row += (palette or b"\x00" * 768)[index * 3:index * 3 + 3] + bytes((alpha,))
        image.append(row)
    return image


# ---- sprites -------------------------------------------------------------

def _mask(operations) -> list[list[str]]:
    grid = [["."] * 16 for _ in range(16)]

    def dot(x, y, char):
        if 0 < x < 15 and 0 < y < 15:
            grid[y][x] = char

    for operation in operations:
        char, kind, *values = operation
        if kind == "line":
            x0, y0, x1, y1, thick = values
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for step in range(steps + 1):
                x = round(x0 + (x1 - x0) * step / steps)
                y = round(y0 + (y1 - y0) * step / steps)
                dot(x, y, char)
                if thick > 1:
                    dot(x + 1, y, char)
                    dot(x, y + 1, char)
        elif kind == "rect":
            x0, y0, x1, y1 = values
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    dot(x, y, char)
        elif kind == "disc":
            cx, cy, radius = values
            for y in range(16):
                for x in range(16):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                        dot(x, y, char)
        elif kind == "clear":
            x0, y0, x1, y1 = values
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    grid[y][x] = "."
    return grid


SPRITES = {
    "sword": [("m", "line", 7, 8, 13, 2, 2), ("d", "line", 4, 7, 9, 12, 1), ("h", "line", 5, 10, 2, 13, 1), ("d", "rect", 2, 13, 2, 13)],
    "pickaxe": [("h", "line", 2, 13, 10, 5, 1), ("m", "line", 3, 3, 8, 2, 2), ("m", "line", 8, 2, 12, 4, 2), ("m", "line", 12, 4, 13, 9, 2)],
    "axe": [("h", "line", 2, 13, 10, 5, 1), ("m", "rect", 7, 2, 12, 6), ("m", "rect", 5, 3, 7, 5), ("m", "rect", 9, 6, 12, 8), ("m", "clear", 12, 2, 12, 2)],
    "shovel": [("h", "line", 2, 13, 9, 6, 1), ("m", "disc", 11, 4, 2.6)],
    "hoe": [("h", "line", 2, 13, 10, 5, 1), ("m", "line", 6, 3, 11, 3, 2), ("m", "line", 11, 3, 12, 6, 2)],
    "helmet": [("m", "rect", 3, 4, 12, 7), ("m", "rect", 4, 3, 11, 3), ("m", "rect", 3, 8, 5, 11), ("m", "rect", 10, 8, 12, 11), ("d", "rect", 6, 7, 9, 7)],
    "chestplate": [("m", "rect", 4, 3, 11, 13), ("m", "rect", 1, 2, 4, 6), ("m", "rect", 11, 2, 14, 6), ("m", "clear", 6, 1, 9, 3), ("d", "rect", 7, 6, 8, 11)],
    "leggings": [("m", "rect", 3, 2, 12, 5), ("m", "rect", 3, 6, 6, 13), ("m", "rect", 9, 6, 12, 13), ("d", "rect", 3, 2, 12, 2)],
    "boots": [("m", "rect", 2, 5, 5, 12), ("m", "rect", 1, 10, 2, 12), ("m", "rect", 10, 5, 13, 12), ("m", "rect", 13, 10, 14, 12), ("d", "rect", 2, 5, 5, 5), ("d", "rect", 10, 5, 13, 5)],
    "food": [("m", "disc", 7.5, 8.5, 4.6), ("h", "line", 8, 4, 9, 2, 1), ("d", "rect", 10, 3, 11, 3)],
    "ingot": [("m", "rect", 3, 7, 12, 10), ("m", "rect", 4, 6, 13, 6), ("m", "rect", 5, 5, 13, 5)],
    "gemstone": [("m", "rect", 5, 4, 10, 11), ("m", "rect", 4, 6, 11, 9), ("m", "rect", 6, 3, 9, 12)],
    "orb": [("m", "disc", 7.5, 7.5, 5.2)],
}
TOOLS = ("sword", "pickaxe", "axe", "shovel", "hoe")
ARMOR = ("helmet", "chestplate", "leggings", "boots")


def sprite(shape: str, style: str, seed: int, size: int = 16) -> Image:
    """Shade and outline one mask. Light comes from the top-left on every sprite."""
    grid = _mask(SPRITES[shape])
    palette = PALETTES[style]
    rng = random.Random(seed)
    image = blank(16, 16)

    def filled(x, y):
        return 0 <= x < 16 and 0 <= y < 16 and grid[y][x] != "."

    for y in range(16):
        for x in range(16):
            char = grid[y][x]
            if char == ".":
                if any(filled(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    edge = palette[0]
                    put(image, x, y, (edge[0] * 0.5, edge[1] * 0.5, edge[2] * 0.5))
                continue
            ramp = HANDLE if char == "h" else palette
            lit = not filled(x - 1, y) or not filled(x, y - 1)
            dark = not filled(x + 1, y) or not filled(x, y + 1)
            index = 3 if lit and not dark else 0 if dark and not lit else 2 if (x * 3 + y * 5) % 7 == 0 else 1
            if char == "d":
                index = max(0, index - 1)
            shift = rng.randint(-4, 4)
            colour = ramp[index]
            put(image, x, y, (colour[0] + shift, colour[1] + shift, colour[2] + shift))
    return scale(image, size // 16)


def block_texture(seed: int, style: str, size: int) -> Image:
    """Soft value-noise block face with a darker rim, matching the 0.4 generator byte for byte."""
    rng = random.Random(seed)
    palette = PALETTES[style]
    coarse = [[rng.random() for _ in range(4)] for _ in range(4)]
    rows: Image = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            fx = x * 3 / max(1, size - 1)
            fy = y * 3 / max(1, size - 1)
            ix, iy = min(2, int(fx)), min(2, int(fy))
            tx, ty = fx - ix, fy - iy
            top = coarse[iy][ix] * (1 - tx) + coarse[iy][ix + 1] * tx
            bottom = coarse[iy + 1][ix] * (1 - tx) + coarse[iy + 1][ix + 1] * tx
            value = top * (1 - ty) + bottom * ty + rng.uniform(-0.12, 0.12)
            if x in (0, size - 1) or y in (0, size - 1):
                value -= 0.20
            index = 0 if value < 0.34 else 1 if value < 0.55 else 2 if value < 0.78 else 3
            red, green, blue = palette[index]
            shift = rng.randint(-5, 5)
            row += bytes((clamp(red + shift), clamp(green + shift), clamp(blue + shift), 255))
        rows.append(row)
    for _ in range(max(2, size // 4)):
        x, y = rng.randrange(size), rng.randrange(size)
        offset = rng.choice((-22, 22))
        pixel = rows[y][x * 4:x * 4 + 3]
        rows[y][x * 4:x * 4 + 3] = bytes(clamp(channel + offset) for channel in pixel)
    return rows


def plank_texture(seed: int, style: str, size: int) -> Image:
    """Horizontal boards with seams and a few knots; reads as furniture wood at any rotation."""
    rng = random.Random(seed)
    palette = PALETTES[style]
    boards = 4
    rows: Image = []
    for y in range(size):
        row = bytearray()
        board = y * boards // size
        seam = y % (size // boards) == size // boards - 1
        joint = (board * 5 + 3) * size // 16 % size
        for x in range(size):
            index = 0 if seam or x == joint else 2 if (x + board * 3) % 6 == 0 else 1
            if not seam and rng.random() < 0.06:
                index = 3
            red, green, blue = palette[index]
            shift = rng.randint(-5, 5) + (board % 2) * 6
            row += bytes((clamp(red + shift), clamp(green + shift), clamp(blue + shift), 255))
        rows.append(row)
    return rows


# ---- box-UV painting (entity and armor textures) --------------------------

def box_faces(u: int, v: int, width: int, height: int, depth: int) -> dict[str, tuple[int, int, int, int]]:
    """Minecraft box-UV layout: face name -> (x, y, w, h) on the texture."""
    return {"up": (u + depth, v, width, depth), "down": (u + depth + width, v, width, depth),  # visual top / bottom
            "west": (u, v + depth, depth, height), "north": (u + depth, v + depth, width, height),
            "east": (u + depth + width, v + depth, depth, height), "south": (u + depth + width + depth, v + depth, width, height)}


FACE_LIGHT = {"up": 2, "north": 1, "south": 1, "east": 1, "west": 1, "down": 0}


def paint_box(image: Image, u: int, v: int, dims: tuple[int, int, int], palette, rng: random.Random, *,
              face: str | None = None, keep=None):
    """Fill one cuboid's faces; ``keep(face, x, y)`` limits painting (used for armor pieces)."""
    for name, (fx, fy, fw, fh) in box_faces(u, v, *dims).items():
        for y in range(fh):
            for x in range(fw):
                if keep and not keep(name, x, y, fw, fh):
                    continue
                index = FACE_LIGHT[name]
                if x in (0, fw - 1) or y in (0, fh - 1):
                    index = max(0, index - 1)
                else:
                    # Irregular mottling reads as hide or stone; a regular grid reads as polka dots.
                    roll = rng.random()
                    index = min(3, index + 1) if roll < 0.16 else max(0, index - 1) if roll > 0.9 else index
                colour = palette[index]
                shift = rng.randint(-5, 5)
                put(image, fx + x, fy + y, (colour[0] + shift, colour[1] + shift, colour[2] + shift))
        if name == "north" and face and fw >= 4 and fh >= 3:
            eye_y = fy + max(1, fh // 3)
            left, right = fx + max(1, fw // 4 - 0), fx + fw - 1 - max(1, fw // 4)
            for eye in (left, right):
                put(image, eye, eye_y, (250, 250, 250) if face == "calm" else (255, 60, 40))
                put(image, eye, eye_y + 1, (24, 20, 28))
            if fw >= 6 and fh >= 6:
                for x in range(fx + fw // 2 - 1, fx + fw // 2 + 1):
                    put(image, x, fy + fh - 2, (palette[0][0] * 0.6, palette[0][1] * 0.6, palette[0][2] * 0.6))


def armor_layers(style: str, seed: int) -> tuple[Image, Image]:
    """Humanoid armor layers in the classic 64x32 layout: layer 1 (head, chest, arms, boots) and layer 2 (leggings)."""
    palette = PALETTES[style]
    first, second = blank(64, 32), blank(64, 32)
    rng = random.Random(seed)
    paint_box(first, 0, 0, (8, 8, 8), palette, rng)          # helmet
    paint_box(first, 16, 16, (8, 12, 4), palette, rng)       # chestplate torso
    paint_box(first, 40, 16, (4, 12, 4), palette, rng)       # arms
    boot = lambda name, x, y, w, h: name == "down" or (name not in ("up", "down") and y >= h - 5)
    paint_box(first, 0, 16, (4, 12, 4), palette, rng, keep=boot)
    legs = lambda name, x, y, w, h: name == "up" or (name not in ("up", "down") and y < h - 3)
    paint_box(second, 0, 16, (4, 12, 4), palette, rng, keep=legs)
    belt = lambda name, x, y, w, h: name not in ("up", "down") and y >= h - 5
    paint_box(second, 16, 16, (8, 12, 4), palette, rng, keep=belt)
    return first, second


def contact_sheet(images: list[Image], columns: int = 8, cell: int = 16, zoom: int = 4, gap: int = 2) -> Image:
    """Lay sprites out on a neutral checker background for a quick visual review."""
    rows_count = (len(images) + columns - 1) // columns
    width = columns * (cell + gap) + gap
    height = rows_count * (cell + gap) + gap
    sheet = blank(width, height)
    for y in range(height):
        for x in range(width):
            tone = 58 if (x // 4 + y // 4) % 2 else 70
            put(sheet, x, y, (tone, tone, tone + 6))
    for index, image in enumerate(images):
        side = len(image)
        step = max(1, side // cell)
        ox = gap + (index % columns) * (cell + gap)
        oy = gap + (index // columns) * (cell + gap)
        for y in range(min(cell, side // step)):
            for x in range(min(cell, len(image[0]) // 4 // step)):
                red, green, blue, alpha = get(image, x * step, y * step)
                if alpha:
                    put(sheet, ox + x, oy + y, (red, green, blue))
    return scale(sheet, zoom)
