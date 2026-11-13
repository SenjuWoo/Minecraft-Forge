"""Java source for generated content, per loader and Minecraft era.

Every generated class is self-contained: NeoForge and Forge pick it up through
their event-bus annotations and Fabric through an entrypoint, so no existing
source file is edited. Names are official Mojang mappings, which all three
bundled toolchains use. A kit exists only for a loader/version this toolkit
compiles in its own CI; elsewhere ``add`` writes assets and data and says so.
"""
from __future__ import annotations

import re

from .shapes import walk_parts

# (family, minecraft) -> (loader glue, API era)
KITS = {("neoforge-mdg", "1.21.1"): ("neoforge", "1.21"), ("fabric-loom", "1.21.1"): ("fabric", "1.21"),
        ("fabric-loom", "1.20.1"): ("fabric", "1.20"), ("forge-fg", "1.20.1"): ("forge", "1.20")}

IMPORTS = {name: "net.minecraft." + path for name, path in {
    "ResourceLocation": "resources.ResourceLocation", "Registries": "core.registries.Registries",
    "BuiltInRegistries": "core.registries.BuiltInRegistries", "Registry": "core.Registry", "Holder": "core.Holder",
    "BlockPos": "core.BlockPos", "Direction": "core.Direction", "Util": "Util", "Mth": "util.Mth",
    "Item": "world.item.Item", "Items": "world.item.Items", "BlockItem": "world.item.BlockItem",
    "CreativeModeTabs": "world.item.CreativeModeTabs", "SpawnEggItem": "world.item.SpawnEggItem",
    "SwordItem": "world.item.SwordItem", "PickaxeItem": "world.item.PickaxeItem", "AxeItem": "world.item.AxeItem",
    "ShovelItem": "world.item.ShovelItem", "HoeItem": "world.item.HoeItem", "Tier": "world.item.Tier",
    "ArmorItem": "world.item.ArmorItem", "ArmorMaterial": "world.item.ArmorMaterial",
    "Ingredient": "world.item.crafting.Ingredient", "BlockPlaceContext": "world.item.context.BlockPlaceContext",
    "FoodProperties": "world.food.FoodProperties", "TagKey": "tags.TagKey", "BlockTags": "tags.BlockTags",
    "SoundEvents": "sounds.SoundEvents", "SoundEvent": "sounds.SoundEvent",
    "Block": "world.level.block.Block", "SoundType": "world.level.block.SoundType",
    "HorizontalDirectionalBlock": "world.level.block.HorizontalDirectionalBlock",
    "BlockBehaviour": "world.level.block.state.BlockBehaviour", "BlockState": "world.level.block.state.BlockState",
    "StateDefinition": "world.level.block.state.StateDefinition", "MapColor": "world.level.material.MapColor",
    "BlockGetter": "world.level.BlockGetter", "Level": "world.level.Level",
    "VoxelShape": "world.phys.shapes.VoxelShape", "Shapes": "world.phys.shapes.Shapes",
    "CollisionContext": "world.phys.shapes.CollisionContext",
    "EntityType": "world.entity.EntityType", "MobCategory": "world.entity.MobCategory", "Mob": "world.entity.Mob",
    "PathfinderMob": "world.entity.PathfinderMob", "Monster": "world.entity.monster.Monster",
    "Player": "world.entity.player.Player", "AttributeSupplier": "world.entity.ai.attributes.AttributeSupplier",
    "Attributes": "world.entity.ai.attributes.Attributes", "FloatGoal": "world.entity.ai.goal.FloatGoal",
    "PanicGoal": "world.entity.ai.goal.PanicGoal", "MeleeAttackGoal": "world.entity.ai.goal.MeleeAttackGoal",
    "WaterAvoidingRandomStrollGoal": "world.entity.ai.goal.WaterAvoidingRandomStrollGoal",
    "LookAtPlayerGoal": "world.entity.ai.goal.LookAtPlayerGoal", "RandomLookAroundGoal": "world.entity.ai.goal.RandomLookAroundGoal",
    "HurtByTargetGoal": "world.entity.ai.goal.target.HurtByTargetGoal",
    "NearestAttackableTargetGoal": "world.entity.ai.goal.target.NearestAttackableTargetGoal",
    "HierarchicalModel": "client.model.HierarchicalModel", "ModelPart": "client.model.geom.ModelPart",
    "ModelLayerLocation": "client.model.geom.ModelLayerLocation", "PartPose": "client.model.geom.PartPose",
    "CubeListBuilder": "client.model.geom.builders.CubeListBuilder", "CubeDeformation": "client.model.geom.builders.CubeDeformation",
    "LayerDefinition": "client.model.geom.builders.LayerDefinition", "MeshDefinition": "client.model.geom.builders.MeshDefinition",
    "PartDefinition": "client.model.geom.builders.PartDefinition", "MobRenderer": "client.renderer.entity.MobRenderer",
    "EntityRendererProvider": "client.renderer.entity.EntityRendererProvider",
}.items()} | {"EnumMap": "java.util.EnumMap", "List": "java.util.List", "MapCodec": "com.mojang.serialization.MapCodec"}

LOADER_IMPORTS = {
    "neoforge": {"SubscribeEvent": "net.neoforged.bus.api.SubscribeEvent", "EventBusSubscriber": "net.neoforged.fml.common.EventBusSubscriber",
                 "DeferredHolder": "net.neoforged.neoforge.registries.DeferredHolder", "RegisterEvent": "net.neoforged.neoforge.registries.RegisterEvent",
                 "BuildCreativeModeTabContentsEvent": "net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent",
                 "EntityAttributeCreationEvent": "net.neoforged.neoforge.event.entity.EntityAttributeCreationEvent",
                 "DeferredSpawnEggItem": "net.neoforged.neoforge.common.DeferredSpawnEggItem", "Dist": "net.neoforged.api.distmarker.Dist",
                 "EntityRenderersEvent": "net.neoforged.neoforge.client.event.EntityRenderersEvent"},
    "forge": {"SubscribeEvent": "net.minecraftforge.eventbus.api.SubscribeEvent", "Mod": "net.minecraftforge.fml.common.Mod",
              "RegistryObject": "net.minecraftforge.registries.RegistryObject", "ForgeRegistries": "net.minecraftforge.registries.ForgeRegistries",
              "RegisterEvent": "net.minecraftforge.registries.RegisterEvent",
              "BuildCreativeModeTabContentsEvent": "net.minecraftforge.event.BuildCreativeModeTabContentsEvent",
              "EntityAttributeCreationEvent": "net.minecraftforge.event.entity.EntityAttributeCreationEvent",
              "ForgeSpawnEggItem": "net.minecraftforge.common.ForgeSpawnEggItem", "Dist": "net.minecraftforge.api.distmarker.Dist",
              "EntityRenderersEvent": "net.minecraftforge.client.event.EntityRenderersEvent"},
    "fabric": {"ModInitializer": "net.fabricmc.api.ModInitializer", "ClientModInitializer": "net.fabricmc.api.ClientModInitializer",
               "ItemGroupEvents": "net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents",
               "FabricDefaultAttributeRegistry": "net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry",
               "EntityRendererRegistry": "net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry",
               "EntityModelLayerRegistry": "net.fabricmc.fabric.api.client.rendering.v1.EntityModelLayerRegistry"},
}
REGISTRY = {"neoforge": {"BLOCK": "Registries.BLOCK", "ITEM": "Registries.ITEM", "ENTITY_TYPE": "Registries.ENTITY_TYPE", "ARMOR_MATERIAL": "Registries.ARMOR_MATERIAL"},
            "forge": {"BLOCK": "BLOCKS", "ITEM": "ITEMS", "ENTITY_TYPE": "ENTITY_TYPES"},
            "fabric": {"BLOCK": "BuiltInRegistries.BLOCK", "ITEM": "BuiltInRegistries.ITEM", "ENTITY_TYPE": "BuiltInRegistries.ENTITY_TYPE",
                       "ARMOR_MATERIAL": "BuiltInRegistries.ARMOR_MATERIAL"}}

BLOCK_PROPERTIES = {
    "stone": ".mapColor(MapColor.STONE).requiresCorrectToolForDrops().strength(1.5F, 6.0F)",
    "wood": ".mapColor(MapColor.WOOD).strength(2.0F, 3.0F).sound(SoundType.WOOD).ignitedByLava()",
    "metal": ".mapColor(MapColor.METAL).requiresCorrectToolForDrops().strength(5.0F, 6.0F).sound(SoundType.METAL)",
    "gem": ".mapColor(MapColor.DIAMOND).requiresCorrectToolForDrops().strength(5.0F, 6.0F).sound(SoundType.AMETHYST)",
    "organic": ".mapColor(MapColor.PLANT).strength(0.6F).sound(SoundType.GRASS)",
    "arcane": ".mapColor(MapColor.COLOR_PURPLE).requiresCorrectToolForDrops().strength(3.0F, 9.0F).sound(SoundType.AMETHYST).lightLevel(state -> 7)",
}
BLOCK_PROPERTIES |= {"ruby": BLOCK_PROPERTIES["gem"], "gold": BLOCK_PROPERTIES["metal"], "bone": BLOCK_PROPERTIES["stone"],
                     "flesh": BLOCK_PROPERTIES["organic"], "leather": BLOCK_PROPERTIES["organic"]}
MINEABLE = {"stone": "pickaxe", "metal": "pickaxe", "gem": "pickaxe", "arcane": "pickaxe", "ruby": "pickaxe", "gold": "pickaxe",
            "bone": "pickaxe", "wood": "axe", "organic": "hoe", "flesh": "hoe", "leather": "hoe"}
# uses, speed, attack bonus, level, enchantability, vanilla repair item, armor durability multiplier, defense (boots, leggings, chestplate, helmet), toughness
TIERS = {"wood": (59, 2.0, 0.0, 0, 15, "minecraft:oak_planks", 5, (1, 2, 3, 1), 0.0),
         "stone": (131, 4.0, 1.0, 1, 5, "minecraft:cobblestone", 7, (1, 3, 4, 1), 0.0),
         "iron": (250, 6.0, 2.0, 2, 14, "minecraft:iron_ingot", 15, (2, 5, 6, 2), 0.0),
         "diamond": (1561, 8.0, 3.0, 3, 10, "minecraft:diamond", 33, (3, 6, 8, 3), 2.0),
         "netherite": (2031, 9.0, 4.0, 4, 15, "minecraft:netherite_ingot", 37, (3, 6, 8, 3), 3.0)}
TIER_TAG = {"wood": "WOODEN", "stone": "STONE", "iron": "IRON", "diamond": "DIAMOND", "netherite": "NETHERITE"}
TOOL_STATS = {"sword": ("SwordItem", "3", "-2.4F"), "pickaxe": ("PickaxeItem", "1", "-2.8F"), "axe": ("AxeItem", "6.0F", "-3.1F"),
              "shovel": ("ShovelItem", "1.5F", "-3.0F"), "hoe": ("HoeItem", "-2", "-1.0F")}
TOOL_TAB = {"sword": "COMBAT"}


def kit_for(family: str, minecraft: str):
    return KITS.get((family, minecraft))


def pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))


def number(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return (text if "." in text else text + ".0") + "F"


def location(era: str, namespace: str, path: str) -> str:
    return (f'ResourceLocation.fromNamespaceAndPath("{namespace}", "{path}")' if era == "1.21"
            else f'new ResourceLocation("{namespace}", "{path}")')


def _finish(package: str, body: str, loader: str, extra: dict[str, str] | None = None) -> str:
    """Prepend the package line and exactly the imports the body uses."""
    table = IMPORTS | LOADER_IMPORTS[loader] | (extra or {})
    used = {table[name] for name in set(re.findall(r"\b[A-Z][A-Za-z0-9]*\b", body)) if name in table}
    used = sorted(name for name in used if name.rsplit(".", 1)[0] != package)
    return f"package {package};\n\n" + "".join(f"import {name};\n" for name in used) + ("\n" if used else "") + body


class Registration:
    def __init__(self, field: str, registry: str, java_type: str, path: str, expression: str, tab: str | None = None):
        self.field, self.registry, self.java_type, self.path, self.expression, self.tab = field, registry, java_type, path, expression, tab


def _expand(expression: str, loader: str) -> str:
    """Resolve the three placeholders that differ per loader: value, holder and spawn egg."""
    get = "" if loader == "fabric" else ".get()"
    expression = re.sub(r"\{REF:(\w+)\}", lambda match: match[1] + get, expression)
    expression = re.sub(r"\{HOLDER:(\w+)\}", lambda match: match[1], expression)
    egg = {"neoforge": "DeferredSpawnEggItem", "forge": "ForgeSpawnEggItem", "fabric": "SpawnEggItem"}[loader]
    return re.sub(r"\{EGG:(\w+):(\w+):(\w+)\}", lambda match: f"new {egg}({match[1]}, {match[2]}, {match[3]}, new Item.Properties())", expression)


def content_class(loader: str, era: str, package: str, mod_id: str, name: str, kind: str, registrations: list[Registration],
                  *, attributes: tuple[str, str] | None = None, extra: dict[str, str] | None = None) -> str:
    """One registration class: fields, registry hooks, creative-tab entries and optional entity attributes."""
    lines = [f"/** Generated by the Minecraft Forge toolkit (add {kind}). Yours to edit: the toolkit never rewrites it. */"]
    tabs: dict[str, list[str]] = {}
    for row in registrations:
        if row.tab:
            tabs.setdefault(row.tab, []).append(row.field)
    ident = "    private static ResourceLocation id(String path) {\n        return " + (
        "ResourceLocation.fromNamespaceAndPath(MOD_ID, path)" if era == "1.21" else "new ResourceLocation(MOD_ID, path)") + ";\n    }\n"
    if loader == "fabric":
        lines.append(f"public final class {name} implements ModInitializer {{")
        lines.append(f'    public static final String MOD_ID = "{mod_id}";')
        for row in registrations:
            if row.registry == "ARMOR_MATERIAL":
                lines.append(f"    public static final Holder<ArmorMaterial> {row.field} = Registry.registerForHolder("
                             f'{REGISTRY[loader][row.registry]}, id("{row.path}"), {_expand(row.expression, loader)});')
            else:
                lines.append(f"    public static final {row.java_type} {row.field} = {_expand(row.expression, loader)};")
        lines += ["", ident, "    @Override", "    public void onInitialize() {"]
        for row in registrations:
            if row.registry != "ARMOR_MATERIAL":
                lines.append(f'        Registry.register({REGISTRY[loader][row.registry]}, id("{row.path}"), {row.field});')
        for tab, fields in tabs.items():
            accepts = " ".join(f"entries.accept({field});" for field in fields)
            lines.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{tab}).register(entries -> {{ {accepts} }});")
        if attributes:
            lines.append(f"        FabricDefaultAttributeRegistry.register({attributes[0]}, {attributes[1]}.createAttributes());")
        lines += ["    }", "}"]
        return _finish(package, "\n".join(lines) + "\n", loader, extra)
    annotation = ("@EventBusSubscriber(modid = {0}.MOD_ID, bus = EventBusSubscriber.Bus.MOD)" if loader == "neoforge"
                  else "@Mod.EventBusSubscriber(modid = {0}.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD)").format(name)
    lines += [annotation, f"public final class {name} {{", f'    public static final String MOD_ID = "{mod_id}";']
    for row in registrations:
        if loader == "neoforge":
            base = {"BLOCK": "Block", "ITEM": "Item", "ENTITY_TYPE": "EntityType<?>", "ARMOR_MATERIAL": "ArmorMaterial"}[row.registry]
            lines.append(f"    public static final DeferredHolder<{base}, {row.java_type}> {row.field} = "
                         f'DeferredHolder.create({REGISTRY[loader][row.registry]}, id("{row.path}"));')
        else:
            lines.append(f"    public static final RegistryObject<{row.java_type}> {row.field} = "
                         f'RegistryObject.create(id("{row.path}"), ForgeRegistries.{REGISTRY[loader][row.registry]});')
    lines += ["", f"    private {name}() {{", "    }", "", ident, "    @SubscribeEvent", "    public static void register(RegisterEvent event) {"]
    for row in registrations:
        expression = _expand(row.expression, loader)
        if loader == "neoforge":
            lines.append(f'        event.register({REGISTRY[loader][row.registry]}, id("{row.path}"), () -> {expression});')
        else:
            lines.append(f'        event.register(ForgeRegistries.Keys.{REGISTRY[loader][row.registry]}, helper -> helper.register(id("{row.path}"), {expression}));')
    lines.append("    }")
    if tabs:
        lines += ["", "    @SubscribeEvent", "    public static void creativeTabs(BuildCreativeModeTabContentsEvent event) {"]
        for tab, fields in tabs.items():
            lines.append(f"        if (event.getTabKey() == CreativeModeTabs.{tab}) {{")
            lines += [f"            event.accept({field}.get());" for field in fields]
            lines.append("        }")
        lines.append("    }")
    if attributes:
        lines += ["", "    @SubscribeEvent", "    public static void attributes(EntityAttributeCreationEvent event) {",
                  f"        event.put({attributes[0]}.get(), {attributes[1]}.createAttributes().build());", "    }"]
    lines.append("}")
    return _finish(package, "\n".join(lines) + "\n", loader, extra)


def client_class(loader: str, package: str, name: str, content: str, entity: str, extra: dict[str, str]) -> str:
    """Client-only renderer and model-layer registration for one mob."""
    model, renderer = entity + "Model", entity + "Renderer"
    if loader == "fabric":
        body = (f"public final class {name} implements ClientModInitializer {{\n    @Override\n    public void onInitializeClient() {{\n"
                f"        EntityRendererRegistry.register({content}.TYPE, {renderer}::new);\n"
                f"        EntityModelLayerRegistry.registerModelLayer({model}.LAYER, {model}::createBodyLayer);\n    }}\n}}\n")
    else:
        annotation = ("@EventBusSubscriber(modid = {0}.MOD_ID, bus = EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)" if loader == "neoforge"
                      else "@Mod.EventBusSubscriber(modid = {0}.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)").format(content)
        body = (f"{annotation}\npublic final class {name} {{\n    private {name}() {{\n    }}\n\n    @SubscribeEvent\n"
                f"    public static void renderers(EntityRenderersEvent.RegisterRenderers event) {{\n"
                f"        event.registerEntityRenderer({content}.TYPE.get(), {renderer}::new);\n    }}\n\n    @SubscribeEvent\n"
                f"    public static void layers(EntityRenderersEvent.RegisterLayerDefinitions event) {{\n"
                f"        event.registerLayerDefinition({model}.LAYER, {model}::createBodyLayer);\n    }}\n}}\n")
    return _finish(package, "/** Generated by the Minecraft Forge toolkit (add mob). Client side only. */\n" + body, loader, extra)


def block_expression(style: str, extra: str = "") -> str:
    return "BlockBehaviour.Properties.of()" + BLOCK_PROPERTIES.get(style, BLOCK_PROPERTIES["stone"]) + extra


def food_expression(era: str, nutrition: int = 4, saturation: float = 0.3) -> str:
    method = "saturationModifier" if era == "1.21" else "saturationMod"
    return f"new Item(new Item.Properties().food(new FoodProperties.Builder().nutrition({nutrition}).{method}({number(saturation)}).build()))"


def tool_expression(era: str, tool: str, tier_class: str) -> str:
    java_class, damage, speed = TOOL_STATS[tool]
    tier = f"{tier_class}.INSTANCE"
    if era == "1.21":
        damage = damage if tool == "sword" else number(float(damage.rstrip("F")))
        return f"new {java_class}({tier}, new Item.Properties().attributes({java_class}.createAttributes({tier}, {damage}, {speed})))"
    return f"new {java_class}({tier}, {damage}, {speed}, new Item.Properties())"


def tier_class(era: str, package: str, name: str, tier: str, repair: str) -> str:
    uses, speed, bonus, level, enchant, default_repair, _, _, _ = TIERS[tier]
    namespace, _, path = (repair or default_repair).partition(":")
    level_method = (f"    @Override\n    public TagKey<Block> getIncorrectBlocksForDrops() {{\n        return BlockTags.INCORRECT_FOR_{TIER_TAG[tier]}_TOOL;\n    }}\n"
                    if era == "1.21" else f"    @Override\n    public int getLevel() {{\n        return {level};\n    }}\n")
    body = f"""/** Tool tier generated by the Minecraft Forge toolkit, starting from vanilla {tier} values. */
public final class {name} implements Tier {{
    public static final {name} INSTANCE = new {name}();

    private {name}() {{
    }}

    @Override
    public int getUses() {{
        return {uses};
    }}

    @Override
    public float getSpeed() {{
        return {number(speed)};
    }}

    @Override
    public float getAttackDamageBonus() {{
        return {number(bonus)};
    }}

{level_method}
    @Override
    public int getEnchantmentValue() {{
        return {enchant};
    }}

    @Override
    public Ingredient getRepairIngredient() {{
        return Ingredient.of(BuiltInRegistries.ITEM.get({location(era, namespace, path)}));
    }}
}}
"""
    return _finish(package, body, "fabric")


def armor_material_expression(mod_id: str, name: str, tier: str, repair: str) -> str:
    """Minecraft 1.21 armor material record (a registry entry there)."""
    _, _, _, _, enchant, default_repair, _, defense, toughness = TIERS[tier]
    namespace, _, path = (repair or default_repair).partition(":")
    boots, leggings, chestplate, helmet = defense
    return ("new ArmorMaterial(Util.make(new EnumMap<>(ArmorItem.Type.class), map -> {\n"
            f"            map.put(ArmorItem.Type.BOOTS, {boots});\n            map.put(ArmorItem.Type.LEGGINGS, {leggings});\n"
            f"            map.put(ArmorItem.Type.CHESTPLATE, {chestplate});\n            map.put(ArmorItem.Type.HELMET, {helmet});\n"
            f"            map.put(ArmorItem.Type.BODY, {chestplate});\n        }}), {enchant}, SoundEvents.ARMOR_EQUIP_IRON, "
            f'() -> Ingredient.of(BuiltInRegistries.ITEM.get(ResourceLocation.fromNamespaceAndPath("{namespace}", "{path}"))), '
            f'List.of(new ArmorMaterial.Layer(ResourceLocation.fromNamespaceAndPath("{mod_id}", "{name}"))), {number(toughness)}, 0.0F)')


def armor_material_class(package: str, name: str, texture_name: str, tier: str, repair: str) -> str:
    """Minecraft 1.20 armor material (an interface there)."""
    _, _, _, _, enchant, default_repair, durability, defense, toughness = TIERS[tier]
    namespace, _, path = (repair or default_repair).partition(":")
    boots, leggings, chestplate, helmet = defense
    body = f"""/** Armor material generated by the Minecraft Forge toolkit, starting from vanilla {tier} values. */
public final class {name} implements ArmorMaterial {{
    public static final {name} INSTANCE = new {name}();

    private {name}() {{
    }}

    @Override
    public int getDurabilityForType(ArmorItem.Type type) {{
        return {durability} * switch (type) {{
            case HELMET -> 11;
            case CHESTPLATE -> 16;
            case LEGGINGS -> 15;
            case BOOTS -> 13;
        }};
    }}

    @Override
    public int getDefenseForType(ArmorItem.Type type) {{
        return switch (type) {{
            case HELMET -> {helmet};
            case CHESTPLATE -> {chestplate};
            case LEGGINGS -> {leggings};
            case BOOTS -> {boots};
        }};
    }}

    @Override
    public int getEnchantmentValue() {{
        return {enchant};
    }}

    @Override
    public SoundEvent getEquipSound() {{
        return SoundEvents.ARMOR_EQUIP_IRON;
    }}

    @Override
    public Ingredient getRepairIngredient() {{
        return Ingredient.of(BuiltInRegistries.ITEM.get(new ResourceLocation("{namespace}", "{path}")));
    }}

    @Override
    public String getName() {{
        return "{texture_name}";
    }}

    @Override
    public float getToughness() {{
        return {number(toughness)};
    }}

    @Override
    public float getKnockbackResistance() {{
        return 0.0F;
    }}
}}
"""
    return _finish(package, body, "fabric")


def furniture_class(era: str, package: str, name: str, shapes: dict[str, list[tuple[float, ...]]]) -> str:
    def shape(boxes):
        parts = [f"Block.box({', '.join(format(value, 'g') for value in box)})" for box in boxes]
        return parts[0] if len(parts) == 1 else "Shapes.or(" + ",\n            ".join(parts) + ")"
    codec = (f"    public static final MapCodec<{name}> CODEC = simpleCodec({name}::new);\n" if era == "1.21" else "")
    codec_method = (f"    @Override\n    protected MapCodec<? extends HorizontalDirectionalBlock> codec() {{\n        return CODEC;\n    }}\n\n"
                    if era == "1.21" else "")
    fields = "".join(f"    private static final VoxelShape {facing.upper()} = {shape(boxes)};\n" for facing, boxes in shapes.items())
    body = f"""/** Furniture block generated by the Minecraft Forge toolkit: faces the player who places it. */
public class {name} extends HorizontalDirectionalBlock {{
{codec}{fields}
    public {name}(BlockBehaviour.Properties properties) {{
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }}

{codec_method}    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {{
        builder.add(FACING);
    }}

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {{
        return defaultBlockState().setValue(FACING, context.getHorizontalDirection().getOpposite());
    }}

    @Override
    public VoxelShape getShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {{
        return switch (state.getValue(FACING)) {{
            case EAST -> EAST;
            case SOUTH -> SOUTH;
            case WEST -> WEST;
            default -> NORTH;
        }};
    }}
}}
"""
    return _finish(package, body, "fabric")


def entity_class(package: str, name: str, hostile: bool, health: float, speed: float, damage: float) -> str:
    base = "Monster" if hostile else "PathfinderMob"
    attributes = ("Monster.createMonsterAttributes()" if hostile else "Mob.createMobAttributes()") + (
        f".add(Attributes.MAX_HEALTH, {health}D).add(Attributes.MOVEMENT_SPEED, {speed}D)"
        + (f".add(Attributes.ATTACK_DAMAGE, {damage}D)" if hostile else ""))
    goals = ("        goalSelector.addGoal(2, new MeleeAttackGoal(this, 1.0D, false));\n"
             "        targetSelector.addGoal(1, new HurtByTargetGoal(this));\n"
             "        targetSelector.addGoal(2, new NearestAttackableTargetGoal<>(this, Player.class, true));\n" if hostile
             else "        goalSelector.addGoal(1, new PanicGoal(this, 1.25D));\n")
    body = f"""/** Mob generated by the Minecraft Forge toolkit. Behaviour lives in registerGoals(); attributes in createAttributes(). */
public class {name} extends {base} {{
    public {name}(EntityType<? extends {base}> type, Level level) {{
        super(type, level);
    }}

    public static AttributeSupplier.Builder createAttributes() {{
        return {attributes};
    }}

    @Override
    protected void registerGoals() {{
        goalSelector.addGoal(0, new FloatGoal(this));
{goals}        goalSelector.addGoal(5, new WaterAvoidingRandomStrollGoal(this, 1.0D));
        goalSelector.addGoal(6, new LookAtPlayerGoal(this, Player.class, 8.0F));
        goalSelector.addGoal(7, new RandomLookAroundGoal(this));
    }}
}}
"""
    return _finish(package, body, "fabric")


def model_class(era: str, package: str, name: str, entity: str, mod_id: str, asset_id: str, rig: dict, extra: dict[str, str]) -> str:
    """HierarchicalModel with the rig's cuboids; walk and look animation from each bone's role."""
    parts = list(walk_parts(rig["parts"]))
    fields = "".join(f"    private final ModelPart {_camel(part['name'])};\n" for part in parts if part["role"])
    lookups, build, animate = [], [], []

    def emit(part, parent_variable, parent_expression):
        variable = _camel(part["name"])
        cubes = "CubeListBuilder.create()" + "".join(
            f".texOffs({cube['uv'][0]}, {cube['uv'][1]})" + (".mirror()" if cube.get("mirror") else "")
            + f".addBox({', '.join(number(value) for value in (*cube['origin'], *cube['size']))}"
            + (f", new CubeDeformation({number(cube['inflate'])})" if cube.get("inflate") else "") + ")"
            for cube in part["cubes"])
        pose = ("PartPose.offsetAndRotation(" + ", ".join(number(value) for value in (*part["pivot"], *part["rotation"])) + ")"
                if any(part.get("rotation", (0, 0, 0))) else "PartPose.offset(" + ", ".join(number(value) for value in part["pivot"]) + ")")
        declaration = f"PartDefinition {variable} = " if part["children"] else ""
        build.append(f'        {declaration}{parent_variable}.addOrReplaceChild("{part["name"]}", {cubes}, {pose});')
        expression = f'{parent_expression}.getChild("{part["name"]}")'
        if part["role"]:
            lookups.append(f"        this.{variable} = {expression};")
        for child in part["children"]:
            emit(child, variable, expression)

    for part in rig["parts"]:
        emit(part, "root", "root")
    for part in parts:
        variable = _camel(part["name"])
        if part["role"] == "head":
            animate += [f"        {variable}.yRot = netHeadYaw * Mth.DEG_TO_RAD;", f"        {variable}.xRot = headPitch * Mth.DEG_TO_RAD;"]
        elif part["role"] in ("leg_a", "leg_b"):
            phase = "" if part["role"] == "leg_a" else " + Mth.PI"
            animate.append(f"        {variable}.xRot = Mth.cos(limbSwing * 0.6662F{phase}) * 1.4F * limbSwingAmount;")
    width, height = rig["texture"]
    body = f"""/** Model generated by the Minecraft Forge toolkit. Edit {asset_id}.bbmodel in Blockbench, then: bbmodel PROJECT FILE --entity {asset_id} --force */
public class {name} extends HierarchicalModel<{entity}> {{
    public static final ModelLayerLocation LAYER = new ModelLayerLocation({location(era, mod_id, asset_id)}, "main");
    private final ModelPart root;
{fields}
    public {name}(ModelPart root) {{
        this.root = root;
{chr(10).join(lookups)}
    }}

    public static LayerDefinition createBodyLayer() {{
        MeshDefinition mesh = new MeshDefinition();
        PartDefinition root = mesh.getRoot();
{chr(10).join(build)}
        return LayerDefinition.create(mesh, {width}, {height});
    }}

    @Override
    public ModelPart root() {{
        return root;
    }}

    @Override
    public void setupAnim({entity} entity, float limbSwing, float limbSwingAmount, float ageInTicks, float netHeadYaw, float headPitch) {{
{chr(10).join(animate)}
    }}
}}
"""
    return _finish(package, body, "fabric", extra)


def renderer_class(era: str, package: str, name: str, entity: str, mod_id: str, asset_id: str, shadow: float, extra: dict[str, str]) -> str:
    body = f"""/** Renderer generated by the Minecraft Forge toolkit. */
public class {name} extends MobRenderer<{entity}, {entity}Model> {{
    private static final ResourceLocation TEXTURE = {location(era, mod_id, f"textures/entity/{asset_id}.png")};

    public {name}(EntityRendererProvider.Context context) {{
        super(context, new {entity}Model(context.bakeLayer({entity}Model.LAYER)), {number(shadow)});
    }}

    @Override
    public ResourceLocation getTextureLocation({entity} entity) {{
        return TEXTURE;
    }}
}}
"""
    return _finish(package, body, "fabric", extra)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    value = head + "".join(part.capitalize() for part in rest)
    return value + "Part" if value in {"root", "entity", "this", "super", "class", "new", "default", "switch", "case"} else value
