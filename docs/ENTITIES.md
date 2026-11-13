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

Give look, physics and other procedural motion their **own bones that no animation keys**. If a keyframed bone is also driven in code, one of them silently wins per frame.

## Controllers and triggered actions

- One looping `base` controller (idle/walk/run, combat variants chosen from synced state) plus separate controllers for one-shot actions (`attack`, `cast`, `draw`) and hurt flinches, each built with `.triggerableAnim(name, RawAnimation.begin().thenPlay(...))` and a predicate that returns `PlayState.STOP`.
- Fire actions on the server with `triggerAnim(controller, name)`; GeckoLib syncs them. Animation-derived state the client needs every frame (weapon in hand, casting) goes in `SynchedEntityData`.
- Time server effects (damage, heal, sound) with ticks counted in the entity, matched to the animation's contact frame; never wait for the client.
- Swap props by toggling bones (`setHidden`) at the frame the hand reaches them: for example `sword_held` vs `sword_sheathed`, `fist` vs `open hand`.
- Death: return `0` from `getDeathMaxRotation` when a death animation lays the model down, or vanilla flips it a second time.
- A floor-length cape, train or tail that must not lift with the walk cycle belongs on its own bone under `root`, not under `body`.

## Rendering

- Layered or semi-transparent textures (glass, thin cloth, ghosts, slime): override `getRenderType` with `RenderType.entityTranslucentCull(texture)`. Cutout drops partial alpha; non-culled translucency sorts hidden inner faces over outer ones.
- Z-fighting: two cubes whose faces share a plane and normal flicker. Check the rest pose in the generator (same-normal faces within ~0.01 px whose rectangles overlap) and push one by a fraction of a pixel or stagger alternating layers. Fix the count to zero before texturing.
- Feet and shoes: give them a separate bone/cube from the leg cuff so the cuff never overlaps the shoe faces at bent poses.
- `withScale(f)` on the renderer scales the whole model; remember it when you convert world motion into model pixels (`16 / scale`).

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
- Tune from a logged trace (offset per tick while walking), not from screenshots: aim for visible motion that never rides the clamp. Expose strength in a client config.

## Custom AI that fits vanilla

- A support/healer mob: one goal that picks the most-wounded ally in range, walks to cast range, faces it, plays the cast, applies the effect at the contact tick, then cools down. A melee goal that only runs when the healer has a target and switches weapon first (draw animation, then attack).
- Villagers are **brain-driven**. A `Goal` added to `villager.goalSelector` in `EntityJoinLevelEvent` still ticks before the brain each tick, so it can win movement if it re-issues its path every tick and sets `WALK_TARGET`; erase `HURT_BY`, `HURT_BY_ENTITY` and `NEAREST_HOSTILE` memories while it runs or the panic behaviour takes over again.
- Village membership: find meeting points with `PoiManager.findAll(h -> h.is(PoiTypes.MEETING), ...)` around players, require a minimum villager count, and record "this village has its unique mob" in `SavedData` keyed by bell position so it survives reloads and respawns after a configurable delay. Adopt an existing nearby instance instead of spawning a duplicate.
- Spawning at runtime: `create(level)`, `moveTo`, `finalizeSpawn(level, difficulty, MobSpawnType.STRUCTURE, null)`, `addFreshEntityWithPassengers`; check a sturdy floor, `noCollision(type.getSpawnAABB(...))` and no fluid first.
- Friendly fire: filter in `hurt` or `LivingIncomingDamageEvent` by attacker type, and gametest it.

## Proving it

Server-side behaviour: GameTests (`guide testing`: arena template, far-from-origin pitfalls, husks). Looks and animation: a client screenshot automation run (`guide testing`, "Client screenshot automation") with a turntable, a UV test, and burst frames of each action. Both are cheaper than asking the user to look.
