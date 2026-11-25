# Building a high-quality mob (GeckoLib, NeoForge 1.21.1)

The path seven finished mob projects converged on, with the commands that now carry the parts each of them built by hand. Use it for a character mob with a custom model, keyframed animation, secondary motion, sounds and real behaviour. For a simple vanilla-rig mob, `add PROJECT mob NAME` is enough.

Related guides: `entities` (conventions and rendering), `api` (verified signatures), `worldgen` (homes, structures, natural spawns), `testing` (GameTests, client run), `audio`.

## The path

```text
minecraft-forge instances                                         # match the pack: Minecraft, loader, GeckoLib build
minecraft-forge quickstart <Mod>/source --mod-id ID --package PKG --name "Name" --no-examples
minecraft-forge libs --add geckolib --project <Mod>/source --version <the pack's version>
minecraft-forge pipeline <Mod>/source --mob NAME                  # <Mod>/asset-pipeline: generators for every asset
python -I <Mod>/asset-pipeline/build_assets.py all --validate     # geo, textures, cube lists, animations, gen/ Java constants
minecraft-forge kit <Mod>/source geomob --mob NAME                # entity, model, renderer, registration, springs
minecraft-forge devshots <Mod>/source --subject ID:NAME           # scripted client screenshot run
minecraft-forge verify <Mod>/source --client                      # compile, package, server load, client run
minecraft-forge devlog <Mod>/source                               # gate the client log (errors, sounds, traces)
```

That is a rendering, animated, sprung example mob in a real client within minutes. The work is then replacing the example in `asset-pipeline/mob/` with the design and growing the entity class.

Extend the pipeline from `mob/`, never by editing `lib/` (which `pipeline --force` refreshes): a project command
(block art from the prop's own shape, overlay textures, a palette measured from the reference) is a module in `mob/`
listed in an optional `mob/commands.py` (`COMMANDS`, and `ALL_ORDER` to put it into `all`). The sprites step calls
`mob/sprites.py` `write_particles()` when it exists. If `lib/` really needs a change, mark each line
`[project patch]`, keep the project off `pipeline --force`, and file a field report so the toolkit absorbs it.

Project layout that every finished project used: `source/` (the Gradle project), `asset-pipeline/` (generators; nothing in it ships), `media/` (review images), `mod/` (staged release JAR and manifest), `docs/` (design, validation), `reference/` (supplied material, read-only).

Several mobs in one mod share one pipeline: `pipeline PROJECT --mob second --add` creates `mobs/second/` beside `mob/` and lists it in pipeline.json `mobs`. Each command runs once per mob in its own process (`--mob a,b` selects); per-mob `build/<mob>/`, `media/<mob>/`, optional `mobs/<mob>/palette.json` and `spring_gains.json`; plan and release run once. Shared rig families or clip libraries go in a package of your own that both mob packages import. One fix point for 13 golems beat 13 pipeline copies.

## Order of work

Risk first, art last. Each line is a stage with its own proof.

1. **Brief to checklist.** Write `mob/look.py` CHECKLIST from the brief in the owner's words: one row per requested feature, mapped to the view that shows it. Write the behaviour list the same way as planned GameTests. A feature without a row gets forgotten.
2. **Facts.** Read `guide api`; spot-check the rows the design depends on against the pinned sources. Record surprises in the project, not in memory.
3. **Rig and blockout.** Bones, pivots, procedural bones and swap groups in `mob/rig.py`; flat-material shapes in `mob/model.py`. `all --validate`, then the client `turntable` and `uv` scenes: orientation, scale against the hitbox, and the per-face UV proof, once.
4. **The riskiest mechanic.** Whatever the mob is defined by (a chain, a transformation, a ranged attack, a carried prop, a two-entity interaction): one working slice in a real client, measured with traces, before final art. If it fails twice, switch to the planned fallback.
5. **Final geometry**, then **paint**, then **clips**: `sheets` and `anim sheet` after every change (seconds), the client run per stage (minutes).
6. **Behaviour** as server-side state machines timed by ticks, each with GameTests: goals, targeting, taming or trading, spawn rules, drops.
7. **Secondary motion**: springs traced and tuned (`build_assets.py springs`).
8. **Sounds** last, when the events they belong to exist.
9. **Release**: full scene run, `devlog` gate, `VALIDATION.md` with an honest untested list, `build_assets.py release`, then `deploy` only on the owner's request.

## Modelling

- Describe organic forms as implicit shapes per bone (`lib/sdf.py`): superellipsoids for chunky masses, tapered capsules for limbs, smooth unions for soft joins, intersections and half-spaces for cut lines. The voxeliser partitions each blob into boxes that cannot z-fight with themselves, shifts blobs by sub-pixel offsets until none of their visible faces share a plane, and drops buried faces. `model --validate` runs the independent `model-check`; the count must be zero before texturing.
- Cell size 0.8-1.0 px on large forms, 0.5 px where the detail lives; 2 texels per pixel, 4 on faces and other focal detail; raw boxes at a higher density for pixel-art plates. About 1,500 cubes is comfortable with several instances on screen.
- Proportion is decided in the blockout. Measure it from the rig (head height against total height, limb lengths) and gate it, instead of judging a painted model.
- A part that must sit at an angle and stay crisp (a socket facing 45 degrees down so it serves both a seated and a
  bent-over pose, an angled plate or visor) hangs from a bone with a rest rotation: a fourth element in `mob/rig.py`
  BONES, `(name, parent, pivot, (rx, ry, rz))`. Author its parts axis-aligned and mark them `local=True` in
  `mob/model.py`: they are built in the bone's unrotated frame, so they stay out of ambient occlusion and the body
  union, and GeckoLib turns them at load time. Voxelising a tilted shape in the model frame gives stair-stepped
  edges instead.
- A body type is a mapping of regions, not a uniform scale. A shortstack built by scaling a normal body down reads as
  a small normal person; shortening the legs breaks every contact solved on them. What held: keep the lower body
  and the pivots the solved clips depend on, scale the torso (about 0.65), arms (0.75) and chest (0.85) down and
  the head up (1.35), and choose the height with the renderer scale (`16 / px per block`). Keep the mapping in one
  module (`mob/proportions.py`) that rig, model and clips import, and re-run the contact gates after any change.
- Overlap parts at joints so bends do not open gaps; give swap variants their own bones and a small stagger; keep a cuff, strap or sole on its own cube so it never fights the limb it sits on.
- Soft layers (clothing, shells, fluid, glass) are separate geometries that share the main bone names (`Part(geo="shell")`), drawn by a layer that copies bone state (`kit PROJECT layer`). Build a shell as the same shapes inflated by 0.35-0.9 px; omit shell faces buried in the body or in another shell. Draw translucent shells with back-face culling so overlapping shells do not double up.
- Faces are flat plates at a higher texel density (6-8 per pixel) just proud of the voxel surface: at body density the eyes come out a few texels wide and unreadable, and a flat plate does not fight the voxel steps. Expressions are swap variants of those plates plus a procedural blink.
- Light that defines the character (an underglow, a rim) is baked into the glow mask and scaled by a synced value; world light cannot guarantee it. labPBR `_n` and `_s` maps cost nothing without shaders and make wet and metal surfaces read with them.
- A feature that is two texels wide is a painted detail, not geometry: a one-texel highlight over a one-texel shadow reads as a ridge and costs no cubes.

## Texture

- Lock the palette first (`palette.json`, 3-5 hard steps per ramp, shadows shifted in hue). `lib/palette.py` `ramp_from_image(ref, boxes, keep=hsv_filter(...))` measures a ramp per material from a reference: generous boxes plus a hue, saturation and value filter so background and neighbours drop out, then anchors (circular-mean hue, median mid-tone saturation, 8th-97th percentile lightness) spaced evenly; k-means gave muddy ramps. Colours the reference does not contain at measurable size (nails, sheer stockings over skin, glints) are derived from measured ramps by mixing, so paint never leaves the palette.
- Review the back and underside: the game shows them mostly in the two darkest bands. Skin whose shadows kept the lit saturation read salmon-red there; lowering shadow saturation (factor about 0.8) brought back the reference's muted tan.
- Paint in 3D: every texel knows its rest position and the smooth normal of its shape (`mob/paint.py`). Markings are conditions on position, so they land correctly on every face of every cube and survive remodelling.
- Hard light bands, no gradients, no anti-aliasing, no dithering; one-texel specular chips on glossy materials; ambient occlusion from the body union darkens folds and undersides.
- Parts that bend at runtime (chain segments, anything a solver poses) must be shaded from normals around their own axis only: a baked top light bands at every joint when the part rotates.
- Glow: return a glow layer from the material; the painter writes `<name>_glowmask.png` only when something glows and copies the glow colour into the base texture at those texels, because GeckoLib 4.9.3 takes a glowing texel's colour from the base texture and only its alpha from the mask (a colour kept only in the mask renders as the dark base texel). Night screenshots are the proof.
- Glow and overlays (wet, flush, dirt) are drawn by passes that redraw only the cubes carrying their texels: the `cubes` step writes `gen/<Mob>Cubes.java` for every layer texture, and the kit's `CubePasses` (`GlowLayer`, `redraw`) uses it with the geomob renderer's cube filter. Measured: glow 1.55 -> 1.03 ms per instance, three overlays 3.45 -> 1.17 ms. Paint overlays on the body's own UVs (same size as the base texture) and fade them on level game time, never `tickCount` (it differs between client and server).
- Many colour variants: bake a texture per variant (or tint one layer) rather than re-rendering the whole model per frame with a tint. A whole-model extra pass costs as much as another instance.

## Animation

- Clips are functions of time returning offsets from rest (`mob/clips.py`): sums of easing curves and oscillators, not tables of keys. Sampling, key reduction, grounding and export are the toolkit's job.
- Ground locomotion and full-body clips on the legs; leave upper-body actions ungrounded and key only upper-body bones in them so the base controller keeps the legs. A hop that must stay planted is a heel-rise, not a root lift.
- `lib/ik.two_bone` points the middle joint toward `pole` (fixed in 1.5.0; before, a negative flex range pointed it away and projects mirrored the pole). Sweep the pole in from the rest direction as a squat deepens so the thigh twists continuously; key rotations are unwrapped to the nearest equivalent Euler triple, so IK output no longer makes controller transitions spin.
- Sample contact clips densely: interpolation between 20 Hz keys put a seated contact 0.78 px off its axis mid-bounce (gate 0.6); 60 Hz gave 0.31. One solver function per family of contact clips (all squats, all seat poses) with its own offline gate script keeps every clip exact.
- Contact is solved, not eyeballed: `lib/ik.py` puts a hand, paw or foot on a point of another bone for the body pose of that frame; when the target is out of reach, add a lean and a shoulder first. Props that change hands use two prop bones (one per owner) swapped at one key; check the swap error in pixels offline.
- A clip built around a fixed contact (a seat, a mount, a held partner or prop) is grounded once by its rest pose so the contact cannot drift; export the anchor points the entity code needs as constants alongside the clip ticks.
- Something that changes hands between the world and the rig (a block the mob uproots, rides or picks up) is one definition: the same shape and paint function build the block model, its texture and the prop bone, the mob faces a cardinal direction, and the hand-off is a visibility flip of identical pixels on one tick (the server removes the block while the prop appears). World-lock the prop bone in the model for the sequence (cancel root motion and the render lift) or easing out of idle moves it.
- Events carry timing: `events={"contact": [0.3]}` becomes a tick constant for the server and a timeline instruction for the client.
- State changes that swap visible geometry (garments, forms, held items) are best driven procedurally from a synced value over a fixed number of ticks, with the server refusing a new change while one runs; a keyframed controller cannot swap geometry sets cleanly.
- Pose changes through a server choreographer: fire the exit one-shot while the synced state already holds the destination, so the base loop is already correct when the one-shot ends (no snap back).

## Secondary motion

`kit PROJECT springs` is the solver; `mob/rig.py` SPRINGS is the data. Read the class comment for the rules. In short: sprung parts hang from `_phys` bones no clip keys; the drive is measured acceleration (animated parent motion per frame, entity translation per tick, turning), integrated in 4 ms steps with the filter inside the steps; long frames and teleports restart the estimators; outputs are soft-clamped; gains come from a traced, scripted client scene so ordinary motion peaks at 65-85 % of each clamp. A scene labels its trace lines with `s.tag("name")`; the client shows a short teleport as three ticks of fast travel, so the solver treats a large velocity step as a jump (a scene that teleports the subject once traced 27 times the clamp before it did).

Chains that must reach somewhere (hoses, ropes, tethers) are a different tool: a verlet chain pinned at one or both ends, simulated in world space on the client, written to sibling segment bones with `BoneMath.writeSegment`. Lessons: a driven chain never carries slack (derive segment length from the arc you want), sub-step with the anchor travel (at most 0.5 px per step) so a snapping hand cannot stretch it, re-seed on a stall frame as on a teleport, trace stretch and gate it (0.9-1.15), and keep an analytic catenary as the fallback.

## Behaviour

- The server decides everything from tick counts; the client draws. Hits land at the clip's contact tick, items spawn at theirs, and a `MCFORGE-TRACE` line can compare where the server spawned something with where the client drew the source.
- Start from the vanilla base that gives the most for free (`TamableAnimal` for owner, sit and follow; `NeutralMob` for anger; `AbstractHorse` for riding) and note what its side effects cost (`guide api`, `guide entities`).
- Goals that script an action take the movement flags and hold the mob still; random idle actions run only when nothing else does.
- Per-instance client state (springs, chain nodes, blink timers) lives in a client-only field of the entity typed `Object`, never in a static.
- Natural spawns, loot and structures are data (biome modifiers, tags, loot tables, structure sets) so a pack can retune them. A mob that belongs to a place gets a home block inside a structure (`kit PROJECT home`, `build_assets.py world`, `guide worldgen`), never an entity stored in the template.
- Config values read in GameTests need safe getters (defaults before the config loads).
- A sequence (a ride, a scene, a ritual) is a server table of (phase, tick) -> effects built from the generated clip tick constants; the entity counts ticks and never waits for the client. One abort path restores everything (blocks, props, wardrobe, camera, items), with a GameTest per abort cause.
- Find blocks the mob needs (food, plants, stations) with a POI type on the right block state (`PoiManager` search), not by scanning blocks every few ticks; the POI updates itself when the block grows or is used.
- Never sync a world position as a float: at large coordinates it is off by about 0.1 block. A seat or camera uses an entity's own double position.
- A boss: one per structure through its home block, no biome spawns; music as a looping streamed sound started and stopped on the client with boss-bar membership. "At most one per world, only after X" is a server spawner gated on SavedData, not a biome modifier.
- Effects on any mob (possession, curses, merges) live in a data attachment on the host, not in a replacement entity: the host keeps its model, loot and identity, and it works on modded mobs and players.
- A titan: author at a native size near 42 px and scale the renderer (1.75 gave a 4.6-block boss at about 2,000 cubes); cell 1.0 px for the body, 0.5 px for face, claws and teeth.
- A creature of any block: texture it at runtime from the block atlas (per-face sprites, procedural UV from rest-pose positions, block tint) instead of baking per block; hand-made variants seed the painter with the vanilla block texture.
- One-of-a-kind companions: `updateInterval(1)` on the entity type makes client-side motion reading smooth.

## Proving it

| Claim | Proof |
|---|---|
| Geometry is clean | `model --validate` (budget, UVs, `model-check` zero) |
| It looks as asked | `sheets --validate` (every checklist row has a current view) and a person or agent actually looking at the sheets |
| Orientation and UV | client `uv` scene, once per model |
| Animation reads | `anim sheet`, then client burst frames per action |
| Behaviour | GameTests, one per rule; negative tests for the things that must not happen |
| Numbers | `devlog` rules over `MCFORGE-TRACE` lines: spring peaks, chain stretch, spawn offsets, frame rate with one and with eight instances |
| It exists in the world | `kit home` GameTests (the home forms one resident), then `verify --client --world normal` with a `locate` scene: structures only generate in a world created with them on |
| Nothing is missing | `devlog` built-ins: script finished, no exception naming the mod, no unknown sound, no missing model or texture |
| Sounds | `audio-check`; say "not listened to" until someone has |

Performance budget that held: about 1 ms of CPU per instance, and eight instances keeping at least 60 % of the empty-scene frame rate. The usual wins: draw glow only for cubes that have glow texels, bake colour variants instead of tint passes, cull back faces on the CPU for closed shells.

## Planning and evidence

- A plan is a task table (`| ID | Task | Status | Depends on | Verify | Evidence |`) where every row has a command or file that proves it. `build_assets.py plan status` updates a row; `plan reprove` reruns every proof at the release commit.
- Keep the plan and state ledgers out of the commits whose hashes they record.
- Evidence tiers are separate claims: compile, package, server load, client load, gameplay. Report the ones that ran.
- GUI: check every screen at GUI scale 2 and 3 in screenshots; long text belongs in a side panel, not inside a 176 px frame.
- Dependencies: every extra library is failure surface in a large pack. First-person seat staging replaced a player-animation library; one data component plus an attribute-modifier event replaced rewriting items.
- A client screenshot run proves rendering, not feel. Say what nobody has checked: sound by ear, the real pack, shaders, multiplayer.
