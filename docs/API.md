# Verified API facts: NeoForge 21.1.265 / Minecraft 1.21.1 / GeckoLib 4.9.3

Signatures and behaviours that finished mods needed, each read from the pinned sources or bytecode and then compiled and run. They save the "look everything up first" task of a new mob project: spot-check the rows you depend on instead of rediscovering them. On another version, treat every row as a lead and re-verify it:

```text
minecraft-forge gradle PROJECT createMinecraftArtifacts        # once: prepares the NeoForge sources jar
minecraft-forge sources --project PROJECT "LivingIncomingDamageEvent"
javap -p -cp <geckolib jar from the Gradle cache> software.bernie.geckolib.cache.object.GeoBone
```

The compiler is the final authority: a row a build contradicts is wrong for your version.

## GeckoLib 4.9.3

Use the build your target pack ships (`inventory --instance PATH`). `libs --add geckolib --project PROJECT --version 4.9.3` resolves the NeoForge file's Modrinth version id (`Grwn5rUB`); a bare version number in a Gradle coordinate can resolve another loader's file.

### GeoBone

| Need | Signature |
|---|---|
| Rotation | `setRotX/Y/Z(float)` radians, `updateRotation(x, y, z)`, `getRotX/Y/Z()` |
| Position | `setPosX/Y/Z(float)` model px, `updatePosition(...)`; **position X is negated at render** (`translate(-posX/16, posY/16, posZ/16)`) |
| Scale | `setScaleX/Y/Z(float)`, `updateScale(...)`; **scale is inherited by child bones** |
| Visibility | `setHidden(boolean)`, `setChildrenHidden(boolean)`, `isHidden()` |
| Rest pose | `getInitialSnapshot()` -> `BoneSnapshot`: `getRotX()`, `getOffsetX()`, `getScaleX()` ... |
| Pivot | `getPivotX/Y/Z()` |
| Tree | `getParent()`, `getChildBones()`, `getCubes()`, `getName()` |
| Tracking | `setTrackingMatrices(true)`, `getWorldPosition()`, `getModelPosition()`, `getLocalSpaceMatrix()`, `getWorldSpaceMatrix()` |

Bone transform, in Blockbench pixel space (front -Z, +X the model's own right side), from `GeoRenderer.renderRecursively` and `RenderUtil`:

```text
M_bone = T(-posX, posY, posZ) * T(pivot) * Rz(rz) * Ry(ry) * Rx(rx) * S(sx, sy, sz) * T(-pivot)
point  = M_root * ... * M_parent * M_bone * p
world  = entity position + Ry(180 - bodyYaw) * (p / 16 * renderScale)      (+ 0.01 block lift)
```

- The loader stores pivots, rotations and cube corners Blockbench-true: it negates the JSON pivot x, rotation x and y, and converts `origin [-x1, y0, z0]` back to `x0`.
- `AnimationProcessor.tickAnimation` runs before `GeoModel.setCustomAnimations`. Bones a clip keys are set every frame. Bones nobody keyed ease back to rest only when their changed-marker is clear, and a value written in `setCustomAnimations` keeps its marker: **write procedural bones absolutely from `getInitialSnapshot()`**; adding to the current value accumulates.
- **Tracked matrices are a frame late and their rotation part is off.** `RenderUtil.translateMatrix` builds an identity-plus-translation matrix and adds it; `GeoEntityRenderer` uses it twice, so `getWorldSpaceMatrix()` has the right translation but its 3x3 is `R*S + 2*I` (local-space matrix: `+ 1*I`) and `m33 = 3`. `getWorldPosition()` is correct. The world matrix adds the un-interpolated entity position (it steps once per tick). For same-frame anchors multiply the bone chain yourself (`kit PROJECT bonemath`).

### Faces and UV (per-face UV, `"uv": {"north": {"uv": [u, v], "uv_size": [w, h]}}`)

From `BakedModelFactory$VertexSet` and `GeoQuad.build` (bytecode), confirmed with a UV test texture in a client. Direction in which u and v grow, in Blockbench space, seen from outside:

| Face | u grows toward | v grows toward |
|---|---|---|
| north (-Z, the front) | -X | down |
| south (+Z) | +X | down |
| east (+X) | -Z | down |
| west (-X) | +Z | down |
| up | -X | -Z |
| down | -X | +Z |

On the four side faces that reads left to right, top to bottom. No east/west swap, no U flip. A face without a UV entry builds no quad (`buildQuad` returns null, `renderCube` skips it): omit buried faces.

### Model, renderer, layers

- `GeoModel<T>`: `getModelResource(T)`, `getTextureResource(T)`, `getAnimationResource(T)`, overridable `getRenderType(T, ResourceLocation)`, `setCustomAnimations(T, long instanceId, AnimationState<T>)`, `getAnimationProcessor().getBone(String)` (null when absent), `getBakedModel(ResourceLocation)`.
- `GeoEntityRenderer<T extends Entity & GeoAnimatable>(EntityRendererProvider.Context, GeoModel<T>)`: `withScale(float)`, `addRenderLayer(GeoRenderLayer<T>)`, `getRenderType(T, ResourceLocation, MultiBufferSource, float)`, `getPackedOverlay(T, float u, float partialTick)`, `getDeathMaxRotation(T)` (protected), `preRender(...)`, `scaleModelForRender(...)`.
- `GeoRenderer.reRender(BakedGeoModel, PoseStack, MultiBufferSource, T, RenderType, VertexConsumer, float partialTick, int light, int overlay, int argb)`: the last argument is an ARGB colour.
- `GeoRenderLayer<T>`: `render(PoseStack, T, BakedGeoModel, RenderType, MultiBufferSource, VertexConsumer, float partialTick, int light, int overlay)`.
- **A second geometry on the same model:** `GeoModel.getBakedModel(other)` calls `AnimationProcessor.setActiveModel` when the location changes, so the processor's bone map becomes the other model's bones and a layer reads its own rest pose back. Fetch extra geometries with `GeckoLibCache.getBakedModels().get(location)` and copy bone state from `getGeoModel().getAnimationProcessor()` (`kit PROJECT layer`).
- `AutoGlowingGeoLayer<T>(GeoRenderer<T>)` reads `<texture>_glowmask.png` beside whatever texture the model returns. Every texture variant needs one; it must have the base texture's dimensions (`Glowmask texture dimensions do not match base texture dimensions!`) and at least one non-transparent texel (`Invalid glow layer texture provided, must have at least one pixel!` crashes texture registration).
- Babies are not scaled for you (`isBaby()` only affects limb swing).

### Animation

- `AnimationController<T>(T, String name, int transitionTicks, AnimationStateHandler<T>)`; chainable `.triggerableAnim(String, RawAnimation)`, `.setCustomInstructionKeyframeHandler(...)`, `.setSoundKeyframeHandler(...)`, `.setParticleKeyframeHandler(...)`, `.setAnimationSpeedHandler(Function<T, Double>)`, `.setAnimationSpeed(double)`; `stop()`, `forceAnimationReset()`, `hasAnimationFinished()`, `isPlayingTriggeredAnimation()`.
- `RawAnimation.begin().thenPlay(name) / thenLoop / thenPlayAndHold / thenPlayXTimes(name, n) / thenWait(ticks)`.
- `AnimationState<T>`: `setAndContinue(RawAnimation)`, `isMoving()`, `getPartialTick()`, `getAnimationTick()`, `getController()`, `getData(DataTicket<D>)`, `getAnimatable()`.
- `GeoEntity.triggerAnim(String controller, String anim)` and `stopTriggeredAnim(...)`: a server call syncs to clients. `GeckoLibUtil.createInstanceCache(GeoAnimatable)`.
- `DataTickets.ENTITY_MODEL_DATA` -> `EntityModelData` record: `netHeadYaw()`, `headPitch()` in degrees, already signed for GeckoLib: add them to the rest rotation.
- Clip `"timeline": {"0.275": "step_l#0;"}` (seconds) entries are custom instruction keyframes; the handler gets `CustomInstructionKeyframeEvent<T>` -> `getKeyframeData().getInstructions()`. They fire on the client only: time server effects with tick constants.
- One-shot clips hold their last frame after they finish until another clip plays on that controller.
- Items: `GeoItem` (`SingletonGeoAnimatable`), `GeoItem.registerSyncedAnimatable(this)`, renderer through `createGeoRenderer(Consumer<GeoRenderProvider>)` and `GeoItemRenderer<T>`.

## NeoForge 21.1.265 / Minecraft 1.21.1

### Entities and combat

| Topic | Fact |
|---|---|
| Synced data | `SynchedEntityData.defineId(Class, EntityDataSerializer<T>)`; `defineSynchedData(SynchedEntityData.Builder)` with `builder.define(accessor, value)`; `entityData.set(key, value)` |
| Attributes | `EntityAttributeCreationEvent.put(type, builder.build())` (mod bus); `Mob.createMobAttributes()` |
| Spawn egg | `DeferredSpawnEggItem(Supplier<EntityType<? extends Mob>>, int background, int foreground, Item.Properties)` |
| Spawn placement | `RegisterSpawnPlacementsEvent.register(type, SpawnPlacementTypes.ON_GROUND, Heightmap.Types, predicate, Operation)` (mod bus) |
| Natural spawns | data: `data/<ns>/neoforge/biome_modifier/*.json` with `"type": "neoforge:add_spawns"`, `biomes`, `spawners` (`type`, `weight`, `minCount`, `maxCount`); `#c:is_snowy` and the other `c:` biome tags cover modded biomes |
| Taming | `TamableAnimal`: `tame(Player)`, `isTame()`, `setTame(boolean, boolean applySideEffects)`, `isOrderedToSit()`, `setInSittingPose(boolean)`, `getOwnerUUID()`; owner target goals need `OwnableEntity` and refuse while ordered to sit |
| Anger | `NeutralMob`: `getRemainingPersistentAngerTime()`, `setPersistentAngerTarget(UUID)`, `startPersistentAngerTimer()`, `addPersistentAngerSaveData`, `readPersistentAngerSaveData(Level, CompoundTag)`, `updatePersistentAnger(ServerLevel, boolean)` |
| Melee | `Mob.doHurtTarget(Entity)`, `isWithinMeleeAttackRange(LivingEntity)`, `getAttackBoundingBox()` (override for reach) |
| Knockback | `LivingEntity.knockback(double strength, double x, double z)`: direction is from the target toward the attacker (it subtracts); add lift to `deltaMovement.y` afterwards and set `hurtMarked = true` so players receive it |
| Damage in | `LivingIncomingDamageEvent` (cancellable): `getSource()`, `getAmount()`, `setAmount(float)`, `setInvulnerabilityTicks(int)` |
| Drops | `LivingDropsEvent` (cancellable): `getDrops()` -> `Collection<ItemEntity>`; `Mob.dropCustomDeathLoot(ServerLevel, DamageSource, boolean)` |
| Death timing | `LivingEntity.tickDeath()` is protected: `deathTime++`, removal at 20; override to wait for a death clip |
| Falls, projectiles | `LivingFallEvent` (`setDistance`, `setDamageMultiplier`); `ProjectileImpactEvent` (`getRayTraceResult()`, `getProjectile()`) |
| Thrown things | `ThrowableProjectile(EntityType, Level)` / `(EntityType, LivingEntity, Level)` are protected; `getDefaultGravity()`; `ThrownItemRenderer(Context)` renders `ItemSupplier.getItem()` |
| Riding | override `Entity.getPassengerAttachmentPoint(Entity, EntityDimensions, float)` (protected); `canAddPassenger(Entity)`; `getControllingPassenger()` (`Mob` returns only a Mob passenger); a player always leaves by sneaking |
| Water | `LivingEntity.canBreatheUnderwater()` is final and reads `#minecraft:can_breathe_under_water`; `Attributes.WATER_MOVEMENT_EFFICIENCY` |
| Type tags | `data/minecraft/tags/entity_type/<name>.json`: `powder_snow_walkable_mobs`, `freeze_immune_entity_types`, `can_breathe_under_water` |
| Persistence | `Mob.removeWhenFarAway(double)`; `PersistenceRequired` for placed ones |
| Tracking rate | `EntityType.Builder.updateInterval(1)` sends positions every tick (default 3): smoother for one-of-a-kind mobs whose client physics reads motion |
| Dimensions | `Entity.changeDimension(DimensionTransition)`; `teleportTo(x, y, z)` |

### Items, data, networking

| Topic | Fact |
|---|---|
| Data components | `DeferredRegister.createDataComponents(Registries.DATA_COMPONENT_TYPE, modid)`, `registerComponentType(name, builder -> builder.persistent(codec).networkSynchronized(streamCodec))`; `DataComponents.CUSTOM_MODEL_DATA`, `CONTAINER` (`ItemContainerContents.fromItems(List<ItemStack>)`), `MAX_DAMAGE`, `JUKEBOX_PLAYABLE` |
| Item model overrides | `{"predicate": {"custom_model_data": n}}` works with the `CUSTOM_MODEL_DATA` component |
| Attribute modifiers | `ItemAttributeModifierEvent`: `addModifier(Holder<Attribute>, AttributeModifier, EquipmentSlotGroup)`, `removeModifier(...)` (game bus) |
| Attachments | `AttachmentType.builder(Supplier<T>)`, `.serialize(Codec<T>)`, `.copyOnDeath()` (needs a serializer), `.sync(StreamCodec)`; registry `NeoForgeRegistries.ATTACHMENT_TYPES`; `setData` on the server pushes the sync |
| Saved data | `SavedData.Factory<T>(Supplier<T>, BiFunction<CompoundTag, HolderLookup.Provider, T>)`; `save(CompoundTag, HolderLookup.Provider)`; `serverLevel.getDataStorage().computeIfAbsent(factory, name)` on the overworld |
| Payloads | `RegisterPayloadHandlersEvent.registrar(version)` -> `playToClient / playToServer / playBidirectional(CustomPacketPayload.Type<T>, StreamCodec<? super RegistryFriendlyByteBuf, T>, IPayloadHandler<T>)`; `PacketDistributor.sendToPlayer / sendToServer` |
| Menus | `IMenuTypeExtension.create((int id, Inventory inv, RegistryFriendlyByteBuf buf) -> ...)`; `serverPlayer.openMenu(provider, buf -> ...)` |
| Loot modifiers | `LootModifier(LootItemCondition[])`, `codecStart(instance)`, `doApply(ObjectArrayList<ItemStack>, LootContext)`; JSON in `data/<ns>/loot_modifiers/` plus `data/neoforge/loot_modifiers/global_loot_modifiers.json` |
| Data maps | `DataMapType.builder(id, registryKey, codec).synced(codec, false).build()`, `RegisterDataMapTypesEvent.register(type)`; JSON `data/<ns>/data_maps/item/<name>.json` |
| Jukebox | `record JukeboxSong(Holder<SoundEvent> soundEvent, Component description, float lengthInSeconds, int comparatorOutput)`; data `data/<ns>/jukebox_song/<name>.json` (`sound_event`, `description`, `length_in_seconds`, `comparator_output` 0-15); `Item.Properties.jukeboxPlayable(ResourceKey<JukeboxSong>)` |
| Paintings | `record PaintingVariant(int width, int height, ResourceLocation assetId)`; data `data/<ns>/painting_variant/<name>.json`, texture `textures/painting/<asset>.png`, tag `minecraft:painting_variant/placeable` |
| Creative tabs | `BuildCreativeModeTabContentsEvent.getTabKey()`, `accept(ItemStack)` |
| Config | `ModConfigSpec`; client screen: `container.registerExtensionPoint(IConfigScreenFactory.class, ConfigurationScreen::new)` |
| Common tags | `Tags.Items.TOOLS` (`c:tools`), `MELEE_WEAPON_TOOLS`, `ARMORS`; `Tags.Biomes.IS_SNOWY` (`c:is_snowy`; frozen_river is not in it) |
| Block break as a player | `CommonHooks.fireBlockBreak(Level, GameType, ServerPlayer, BlockPos, BlockState)` posts `BlockEvent.BreakEvent`; `ServerPlayerGameMode.destroyBlock(BlockPos)` is the full vanilla path |
| Light without a block | place `Blocks.LIGHT.defaultBlockState().setValue(LightBlock.LEVEL, n)` only into air, remember the position, remove it on every exit path |

### Client

| Topic | Fact |
|---|---|
| Renderers | `EntityRenderersEvent.RegisterRenderers.registerEntityRenderer(type, provider)` (mod bus, client) |
| Particles | `RegisterParticleProvidersEvent.registerSpriteSet(ParticleType<T>, SpriteParticleRegistration<T>)`; a liquid drip needs its own type (vanilla `DripParticle` tints water in code) |
| Keys, HUD | `RegisterKeyMappingsEvent.register(KeyMapping)`; `RegisterGuiLayersEvent.registerAbove(VanillaGuiLayers.HOTBAR, id, layer)` |
| World render | `RenderLevelStageEvent`: `getStage()`, `getPoseStack()`, `getPartialTick()`, `getCamera()`; stages `AFTER_ENTITIES`, `AFTER_TRANSLUCENT_BLOCKS`, `AFTER_PARTICLES`, `AFTER_WEATHER` |
| Item decorations | `RegisterItemDecorationsEvent.register(ItemLike, IItemDecorator)` |
| Item in the world | `ItemRenderer.renderStatic(LivingEntity, ItemStack, ItemDisplayContext, boolean leftHand, PoseStack, MultiBufferSource, Level, int light, int overlay, int seed)` |
| Custom render type | the `RenderType` constructor is public: `new RenderType(name, DefaultVertexFormat.NEW_ENTITY, VertexFormat.Mode.QUADS, 1536, false, true, setup, clear) {}` |
| Entity lighting | `com.mojang.blaze3d.platform.Lighting`: `DIFFUSE_LIGHT_0 = normalize(0.2, 1, -0.7)`, `DIFFUSE_LIGHT_1 = normalize(-0.2, 1, 0.7)`; `shade = min(1, 0.6 (max(0, n.L0) + max(0, n.L1)) + 0.4)` |
| First launch | a new game directory opens `AccessibilityOnboardingScreen` before `TitleScreen`; set `options.onboardAccessibility = false` |
| Subscribers | `@EventBusSubscriber(modid = ..., value = Dist.CLIENT)` routes mod-bus and game-bus events by type on 21.1.265; the `bus` parameter is deprecated for removal |

### Worldgen and tests

| Topic | Fact |
|---|---|
| Structures | `Structure(StructureSettings)`, `simpleCodec(...)`, `findGenerationPoint(GenerationContext)` -> `Optional<GenerationStub>`; `ChunkGenerator.getBaseColumn(x, z, heightAccessor, randomState)` returns the noise column including aquifer fluids |
| Templates | `data/<ns>/structure/<name>.nbt`, `DataVersion` 3955 (`SharedConstants.WORLD_VERSION`); entities are allowed in templates |
| GameTest | `GameTestHelper.absolutePos` offsets from the structure block; the bundled arena's floor is relative y = 1, mobs stand at y = 2; `makeMockServerPlayerInLevel()` returns a `ServerPlayer` in the test level (deprecated for removal: check on newer builds) |
| Chest season | `ChestRenderer` reads the calendar (24-26 December); mirror the check with a test override rather than the clock |
