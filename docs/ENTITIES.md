# Animated entities (GeckoLib) and custom AI

For mobs beyond `add PROJECT mob` (vanilla `EntityModel` rigs): keyframed animation, many bones, weapon swaps, secondary motion and custom behaviour. Measured on NeoForge 21.1.265 / Minecraft 1.21.1 with GeckoLib 4.9.3; recheck the conventions below against the GeckoLib version you pin (`sources --project PATH "GeoBone"` or `javap`).

## Dependency

`libs --add geckolib --project PATH` writes an exact version. By hand on NeoForge 1.21.1:

```groovy
repositories { maven { name = 'GeckoLib'; url = 'https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/' } }
dependencies { implementation "software.bernie.geckolib:geckolib-neoforge-${minecraft_version}:${geckolib_version}" }
```

Declare it as a required dependency in `neoforge.mods.toml` too. If the user plays a pack, pin the GeckoLib build that pack ships (`inventory --instance PATH`), not the newest.

## Files and classes

| Piece | Path / class |
|---|---|
| Geometry | `assets/<mod>/geo/entity/<name>.geo.json` (Bedrock `format_version` 1.12.0) |
| Animations | `assets/<mod>/animations/entity/<name>.animation.json` (Bedrock 1.8.0 layout) |
| Texture | `assets/<mod>/textures/entity/<name>.png` |
| Model | `extends GeoModel<E>`: three resource getters; per-frame bone code in `setCustomAnimations` |
| Renderer | `extends GeoEntityRenderer<E>`, registered in `EntityRenderersEvent.RegisterRenderers` (client only) |
| Entity | `implements GeoEntity`; `AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this)` |

## Coordinate conventions (the part that costs the most iterations)

If you write `.geo.json` or animation JSON from a script instead of exporting from Blockbench, mirror Blockbench's Bedrock export exactly. GeckoLib undoes it at load time.

| Value | Written to JSON |
|---|---|
| Bone/cube `rotation` (rx, ry, rz) | `[-rx, -ry, rz]` |
| Bone/cube `pivot` (x, y, z) | `[-x, y, z]` |
| Cube `origin` for a box from x0..x1 | `[-x1, y0, z0]` (size stays positive) |
| Animation rotation keyframe | `[-rx, -ry, rz]` |
| Animation position keyframe | `[-px, py, pz]` |
| Face UV keys (`north`, `east`, ...) | Unchanged: no east/west swap, no U flip, when you use per-face UV (`"uv": {"north": {"uv": [u, v], "uv_size": [w, h]}}`) |

Facts that follow from that:

- Animation rotation is **added** to the bone's rest rotation, not substituted. Author poses as offsets from rest.
- Front is north (-Z). Blockbench +X is the model's own right side as it faces you: name bones by the model's side (`arm_right`), not the viewer's, or write down which you chose.
- Per-face UV direction, seen from outside the cube: `u` runs left to right on the side faces; `up` maps u along +X and v along +Z; `down` maps v along -Z. A UV-ramp texture rendered in the client proved all six.
- Prove orientation once with a UV test texture: paint every face as a dark-to-bright left-to-right ramp with a letter, render front/back/both sides in the client, and check each face reads correctly from outside. A swapped east/west or flipped U shows up immediately; guessing it from code does not.

## Head look and procedural bones

`setCustomAnimations` runs after keyframes each frame. `EntityModelData` (`state.getData(DataTickets.ENTITY_MODEL_DATA)`) already carries the sign GeckoLib needs, so **add** it:

```java
GeoBone neck = getAnimationProcessor().getBone("neck");
EntityModelData d = state.getData(DataTickets.ENTITY_MODEL_DATA);
float pitch = Mth.clamp(d.headPitch(), -40f, 40f) * Mth.DEG_TO_RAD;
float yaw = Mth.clamp(d.netHeadYaw(), -70f, 70f) * Mth.DEG_TO_RAD;
neck.setRotX(neck.getInitialSnapshot().getRotX() + pitch);   // absolute from rest: never accumulates
neck.setRotY(neck.getInitialSnapshot().getRotY() + yaw);
```

Give look, physics and other procedural motion their **own bones that no animation keys**, in every animation. If a keyframed bone is also driven in code, one of them silently wins per frame, and a bone keyed by one animation drifts while the controller blends into or out of it (a root bone keyed in a gallop fought a procedural baby offset; the bob moved to `body`).

## Controllers and triggered actions

- One looping `base` controller (idle/walk/run, combat variants chosen from synced state) plus separate controllers for one-shot actions (`attack`, `cast`, `draw`) and hurt flinches, each built with `.triggerableAnim(name, RawAnimation.begin().thenPlay(...))` and a predicate that returns `PlayState.STOP`.
- Fire actions on the server with `triggerAnim(controller, name)`; GeckoLib syncs them. Animation-derived state the client needs every frame (weapon in hand, casting) goes in `SynchedEntityData`.
- **Predicates run on the client.** Read synced data or positions there, never server-only fields: `AbstractHorse#isJumping()` is a server field, so a jump animation keyed on it never plays. A working client test for "in the air": `!onGround() && !isInWater() && !onClimbable() && Math.abs(getY() - yo) > 0.04`. Horse flags that are synced and smooth: `isEating()`, `isStanding()`, `isSaddled()`, `isTamed()`, and the interpolated `getEatAnim(pt)`, `getStandAnim(pt)`, `getMouthAnim(pt)` that vanilla's own horse model uses.
- Time server effects (damage, heal, sound) with ticks counted in the entity, matched to the animation's contact frame; never wait for the client.
- Swap props by toggling bones (`setHidden`) at the frame the hand reaches them: for example `sword_held` vs `sword_sheathed`, `fist` vs `open hand`.
- Death: return `0` from `getDeathMaxRotation` when a death animation lays the model down, or vanilla flips it a second time.
- A floor-length cape, train or tail that must not lift with the walk cycle belongs on its own bone under `root`, not under `body`.

## Rendering

- Layered or semi-transparent textures (glass, thin cloth, ghosts, slime): override `getRenderType` with `RenderType.entityTranslucentCull(texture)`. Cutout drops partial alpha; non-culled translucency sorts hidden inner faces over outer ones.
- Z-fighting: two cubes whose faces share a plane and normal flicker. Check the rest pose in the generator (same-normal faces within ~0.01 px whose rectangles overlap) and push one by a fraction of a pixel or stagger alternating layers. Fix the count to zero before texturing.
- Feet and shoes: give them a separate bone/cube from the leg cuff so the cuff never overlaps the shoe faces at bent poses.
- `withScale(f)` on the renderer scales the whole model; remember it when you convert world motion into model pixels (`16 / scale`).
- **Babies are not scaled for you.** `GeoEntityRenderer` uses `isBaby()` only for limb swing. Override `scaleModelForRender(...)` and scale when `!isReRender`; the base method already skips re-renders, so layers do not scale twice.
- Layers re-render the same baked model with `getRenderer().reRender(bakedModel, poseStack, bufferSource, animatable, renderType, bufferSource.getBuffer(renderType), partialTick, packedLight, packedOverlay, argbColour)`; any other loaded geo comes from `getGeoModel().getBakedModel(ResourceLocation)`.
- `AutoGlowingGeoLayer` looks for `<texture>_glowmask.png` next to whatever texture the model returns, so every texture variant (baby, skins, armor) needs its own glowmask file, even an empty one.
- Per-texel cutout works with the default `entityCutoutNoCull`: hair strand tips, chain-link holes and see-through straps need no translucent type. Use translucency only for partial alpha.
- Run `model-check FILE` (`.bbmodel`, `.geo.json` or a block model) after every generator change: it lists same-facing, coplanar, overlapping faces in the rest pose, skips overlaps another cube covers (by containing or touching them from outside), and exits 1 while any remain. Every cube counts as opaque: re-check see-through cubes by eye. It compares cubes that share one rotation frame; check rotated parts and posed frames in a render.

## Secondary motion (hair, cloth, tails, dangling props, soft bodies)

Cheap and convincing: a damped spring per degree of freedom, evaluated per rendered frame on the client and written as bone offsets.

```java
// x = offset, v = velocity; k stiffness, c damping, force from measured acceleration
v += (-k * x - c * v + force) * h;  x += v * h;
```

- Drive it from **measured** acceleration of the bone's world position (entity position plus the animated parent bone offsets), low-passed (`a += (raw - a) * min(1, dt * 28)`), so walk bob, jumps, turns and knockback all feed it without per-animation code.
- Integrate in fixed sub-steps (`h <= 4 ms`), clamp inputs (teleports produce huge spikes) and re-seed with no impulse when `dt > 0.25 s` (pause, chunk reload).
- Store state per entity instance (a client-only field on the entity, typed as `Object`), never in a static.
- Add an impulse on `hurtTime` rising for hit reactions. Use slightly different stiffness on paired parts so they never move in lockstep.
- Tune from a logged trace (every spring's offset per tick while walking and galloping, next to its clamp), not from screenshots: aim for peaks at about 65-85 % of the clamp. A first tuning that rides the clamp at full speed looks stiff. Expose strength in a client config.

## Recipes that worked (NeoForge 1.21.1, GeckoLib 4.9.3)

**Rideable horse-type mob.** Extend `AbstractHorse` and mirror `Horse`'s overrides (sounds, `mobInteract`, `containerChanged`, `randomizeAttributes`, `canUseSlot`, `isBodyArmorItem`): taming, temper, inventory screen, riding and jumping come for free. Vanilla horse values: `EntityType.Builder.sized(1.3964844f, 1.6f).eyeHeight(1.52f).passengerAttachments(1.44375f)`, renderer scale 1.1; baby dimensions are `withAttachments(PASSENGER at height + 0.125).scale(0.5f)`. `canMate` across species is one-sided (vanilla `Horse` refuses unknown types), so restrict breeding to the same type.

**Horse armor on a custom model.** Armor is the `BODY` slot; the horse screen shows the slot when `canUseSlot(EquipmentSlot.BODY)` is true; `isBodyArmorItem` is an `AnimalArmorItem` with `BodyType.EQUESTRIAN`; vanilla armor values are leather 3, iron 5, gold 7, diamond 11; undyed leather's colour is `-6265536`; get the material name with `armor.getMaterial().unwrapKey()`. Technique: put armor shell cubes in the rig and leave their texels transparent in the base texture, then add a layer that re-renders the same model with a per-material texture where only the shells are painted (cutout discards the rest), tinted for dyed leather. No second model, and the armor follows every animation.

**Outline glow (inverted hull).** A second geo with the same bone names and slightly inflated cubes. Each frame copy rotation, position, scale and hidden state from the main bones, then render it with a custom type: `new RenderType(name, DefaultVertexFormat.NEW_ENTITY, VertexFormat.Mode.QUADS, 1536, false, true, setup, clear) {}` (the constructor is public in 1.21.1), where `setup` calls `RenderType.entityTranslucentEmissive(texture, false).setupRenderState()`, then `RenderSystem.enableCull(); GL11.glCullFace(GL11.GL_FRONT)`, and `clear` restores `GL_BACK`. Keep it subtle: shells about 0.1-0.45 px and alpha at most about 60/255 (0.2-0.7 px at alpha 112 was too strong); use a few boxes that follow round silhouettes, not one bounding box; fade alpha with the light at the entity (`LightTexture.block/sky(packedLight)` times `ClientLevel#getSkyDarken`), because emissive shells glare at night.

## Voxel models from implicit shapes (`voxel`)

For organic parts with many cubes, describe shapes instead of placing boxes: `voxel SPEC.json --project PATH` (or `--out DIR`). Start from `templates/voxel/example.json`.

- Shapes: `ellipsoid`, `superellipsoid` (exponent > 2 gives squarer, chunkier forms), tapered `capsule` (limbs, tails, horns), `box`, `union`, `smooth_union` (k about 0.3-0.8 blends parts softly), `subtract`. Coordinates are Blockbench model pixels, y up, front north (-Z). Each blob belongs to a bone and has a colour.
- Each blob is voxelized on a grid and greedy-merged into a **partition** of boxes. A partition never has two same-facing coplanar faces that overlap, so a blob cannot z-fight with itself. Each blob then tries sub-pixel grid offsets (multiples of 0.03 px) until none of its visible faces lies on a visible face of an earlier blob. The result includes a `model-check` report; a 941-cube model built this way reported zero visible overlaps without manual nudging.
- Faces covered by the blob's own voxels are left out of the per-face UV map. GeckoLib 4.9.3 builds no quad for a missing face (`BakedModelFactory.buildQuad` returns null when the face has no UV; `GeoRenderer.renderCube` skips it), so hidden faces cost neither draw time nor atlas space: about a quarter of all faces on a large model.
- Cell size: 0.6-1.0 px reads as clean Minecraft steps; 0.5 px or finer looks noisy under vanilla face lighting and doubles the cube count. `texels_per_pixel` (default 2) sets texture density; `cell` can differ per blob (eyes, claws).
- Output: `geo/entity/NAME.geo.json`, `textures/entity/NAME.png` (flat blob colours with light noise, a base to paint over), and `blockbench/NAME.bbmodel` plus `NAME_uvtest.png` (dark-to-bright left to right per face, one hue per direction) for orientation checks.
- Painting a large atlas: shade every texel from its rest-pose position and the analytic normal of its shape, vectorized per cube face (numpy). A per-texel Python loop is an order of magnitude slower at about 1,000 cubes.

## Previews that match the game

`preview PROJECT FILE.geo.json` renders GeckoLib geometry with the game's entity lighting: per face, `shade = min(1, 0.6 * (max(0, n.L0) + max(0, n.L1)) + 0.4)` with `L0 = normalize(0.2, 1, -0.7)` and `L1 = normalize(-0.2, 1, 0.7)` (`com.mojang.blaze3d.platform.Lighting`). `--animation FILE --clip walk --time 0.4` poses it. Physically based lights in Blender make backs black and voxel steps look like noise, which misleads tuning; in Blender, apply the same formula as an emission multiplier on the cutout texture (a vertex colour per quad) and in-game screenshots match the previews.

## Grounded animations (`ground`)

`ground ANIM.animation.json --geo MODEL.geo.json --legs leg_l,leg_r --clips walk,run,sit,death` keys the root bone's position so the lowest point of the leg geometry (the listed bones and their children) sits at y = 0 on every keyframe time (`--fps N` samples more). Wide stances, squats, kneeling deaths and lunges stay planted without hand-tuned root offsets. It writes a new file (`NAME.grounded.animation.json` by default).

- Ground locomotion and full-body clips. Leave upper-body actions (attacks, reactions) ungrounded and key only upper-body bones in them, so the base controller keeps driving the legs.
- The evaluator works in Blockbench space, as GeckoLib does after loading: geometry x mirrored back, rotations `[-rx, -ry, rz]` added to rest, positions `[-px, py, pz]`, bone transform `T(position) * T(pivot) * Rz * Ry * Rx * S * T(-pivot)` (GeckoLib's `RenderUtil` rotates Z, then Y, then X). On a shipped 941-cube model it reproduced in-game-proven root offsets to within 0.001 px. Molang expressions cannot be evaluated offline and are refused.

## Water, reach, taming and particles (NeoForge 1.21.1)

- Breathing underwater is an entity type tag: `LivingEntity.canBreatheUnderwater()` is final and reads `#minecraft:can_breathe_under_water`; add your type to `data/minecraft/tags/entity_type/can_breathe_under_water.json`. Full speed in water is the `WATER_MOVEMENT_EFFICIENCY` attribute (1.0).
- Longer melee reach without a bigger hitbox: override `Mob.getAttackBoundingBox()`.
- `TamableAnimal` sitting: the vanilla owner target goals refuse while the animal is ordered to sit (`OwnerHurtByTargetGoal` checks `isOrderedToSit()`), and `FollowOwnerGoal` stops. A "guard this spot" behaviour needs its own target goal that runs while sitting, plus a goal that manages the sitting pose and walks back to the post.
- Vanilla drip particles are tinted in code: `DripParticle` colours water (0.2, 0.3, 1.0), so `dripping_water` always reads as blue. For another liquid, register a `SimpleParticleType`, add `assets/<mod>/particles/<name>.json` listing `minecraft:drip_hang`, `minecraft:drip_fall` and `minecraft:drip_land`, and a sprite-set provider (`RegisterParticleProvidersEvent.registerSpriteSet`) whose particle picks `sprites.get(phase, 2)` and sets its own colour, alpha and `ParticleRenderType.PARTICLE_SHEET_TRANSLUCENT`.
- Particle spawn points on an animated mob should follow the pose: precompute per-pose positions from the rig with the same evaluator the animations use (the toolkit's `mcforge.geckopose` module).

## Custom AI that fits vanilla

- A support/healer mob: one goal that picks the most-wounded ally in range, walks to cast range, faces it, plays the cast, applies the effect at the contact tick, then cools down. A melee goal that only runs when the healer has a target and switches weapon first (draw animation, then attack).
- Villagers are **brain-driven**. A `Goal` added to `villager.goalSelector` in `EntityJoinLevelEvent` still ticks before the brain each tick, so it can win movement if it re-issues its path every tick and sets `WALK_TARGET`; erase `HURT_BY`, `HURT_BY_ENTITY` and `NEAREST_HOSTILE` memories while it runs or the panic behaviour takes over again.
- Village membership: find meeting points with `PoiManager.findAll(h -> h.is(PoiTypes.MEETING), ...)` around players, require a minimum villager count, and record "this village has its unique mob" in `SavedData` keyed by bell position so it survives reloads and respawns after a configurable delay. Adopt an existing nearby instance instead of spawning a duplicate.
- Spawning at runtime: `create(level)`, `moveTo`, `finalizeSpawn(level, difficulty, MobSpawnType.STRUCTURE, null)`, `addFreshEntityWithPassengers`; check a sturdy floor, `noCollision(type.getSpawnAABB(...))` and no fluid first.
- Friendly fire: filter in `hurt` or `LivingIncomingDamageEvent` by attacker type, and gametest it.

## Proving it

Before the client: `model-check` for z-fighting, `preview FILE.geo.json --animation ... --clip ... --time ...` for poses under game lighting, and optionally a headless Blender render (alpha-clipped, nearest-neighbour filtering). They catch most look and animation problems in seconds. The client run stays the proof: `devshots PROJECT` then `verify PROJECT --client`.

Server-side behaviour: GameTests (`guide testing`: arena template and its stand height, far-from-origin pitfalls, husks, breeding and spawn-settings tests). Looks and animation: a client screenshot automation run (`guide testing`, "Client screenshot automation") with a turntable, a UV test, and burst frames of each action. Both are cheaper than asking the user to look.
