"""Look-dev sheets and the look gate: mob/look.py lists the views to render and a checklist that maps every
feature the brief asks for to the view that shows it. `sheets` renders them under game lighting to
media/look/; `sheets --validate` fails when a checklist row names a view that is missing or older than the
model, so "it is built" always comes with a current picture someone can look at.

Look at the sheets yourself before the client run: most proportion, colour and placement problems show here in
seconds. The client run stays the proof.
"""
from __future__ import annotations

from . import animtools, modeltools, paths
from .render import Model, render, sheet

OUT = paths.MEDIA / "look"


def run(args) -> int:
    from mob import look as L
    OUT.mkdir(parents=True, exist_ok=True)
    glow = paths.TEX / f"{paths.MOB}_glowmask.png"
    m = Model(paths.GEO / f"{paths.MOB}.geo.json", paths.TEX / f"{paths.MOB}.png", glow if glow.exists() else None)
    base_hidden = animtools.default_hidden()
    images, labels = [], []
    for v in L.VIEWS:
        hidden = (base_hidden | set(v.get("hide", ()))) - set(v.get("show", ()))
        img = render(m, v.get("yaw", 0), v.get("pitch", 8), v.get("scale", 8.0), size=v.get("size", (300, 380)),
                     hidden=hidden, light=v.get("light", 1.0), center=v.get("center"))
        from PIL import Image
        Image.fromarray(img).save(OUT / f"{v['name']}.png")
        images.append(img)
        labels.append(v["name"])
    sheet(images, labels, cols=min(4, len(images))).save(OUT / "sheet.png")
    rows = ["# Look checklist", "", "| Id | What to look for | Views |", "|---|---|---|"]
    rows += [f"| [{key}] | {what} | {', '.join(views)} |" for key, (what, views) in L.CHECKLIST.items()]
    paths.write_text(OUT / "CHECKLIST.md", "\n".join(rows) + "\n")
    print(f"sheets: {len(images)} views in {OUT}, checklist of {len(L.CHECKLIST)} rows")
    return 0


def validate(args) -> int:
    from mob import look as L
    errs = []
    built = (paths.GEO / f"{modeltools.geo_name()}.geo.json").stat().st_mtime
    names = {v["name"] for v in L.VIEWS}
    for key, (what, views) in L.CHECKLIST.items():
        if not views:
            errs.append(f"[{key}] names no view")
        for view in views:
            file = OUT / f"{view}.png"
            if view not in names:
                errs.append(f"[{key}] view {view} is not in VIEWS")
            elif not file.exists():
                errs.append(f"[{key}] view {view}.png does not exist")
            elif file.stat().st_mtime < built - 1:
                errs.append(f"[{key}] view {view}.png is older than the model")
    for e in errs:
        print("LOOK ERROR:", e)
    print(f"look validate: {len(errs)} error(s)")
    return 1 if errs else 0
