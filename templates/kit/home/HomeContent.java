package @PACKAGE@.@NAME@.home;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.SoundType;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.levelgen.structure.StructureType;
import net.minecraft.world.level.levelgen.structure.pieces.StructurePieceType;
import net.minecraft.world.level.material.MapColor;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.RegisterEvent;

/** Registration of the home block, its block entity, the anchored structure type and its piece. Self-registering. */
@EventBusSubscriber(modid = @PASCAL@HomeContent.MOD_ID)
public final class @PASCAL@HomeContent {
    public static final String MOD_ID = "@MODID@";
    public static final DeferredHolder<Block, @PASCAL@HomeBlock> BLOCK = DeferredHolder.create(Registries.BLOCK, id("@NAME@_home"));
    public static final DeferredHolder<Item, Item> ITEM = DeferredHolder.create(Registries.ITEM, id("@NAME@_home"));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<@PASCAL@HomeBlockEntity>> BLOCK_ENTITY =
            DeferredHolder.create(Registries.BLOCK_ENTITY_TYPE, id("@NAME@_home"));
    public static final DeferredHolder<StructureType<?>, StructureType<@PASCAL@HomeStructure>> STRUCTURE_TYPE =
            DeferredHolder.create(Registries.STRUCTURE_TYPE, id("@NAME@_home"));
    public static final DeferredHolder<StructurePieceType, StructurePieceType> PIECE_TYPE =
            DeferredHolder.create(Registries.STRUCTURE_PIECE, id("@NAME@_home_piece"));

    private @PASCAL@HomeContent() {
    }

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    @SubscribeEvent
    public static void register(RegisterEvent event) {
        event.register(Registries.BLOCK, id("@NAME@_home"), () -> new @PASCAL@HomeBlock(BlockBehaviour.Properties.of()
                .mapColor(MapColor.STONE).strength(50f, 1200f).sound(SoundType.STONE)));
        event.register(Registries.ITEM, id("@NAME@_home"), () -> new BlockItem(BLOCK.get(), new Item.Properties()));
        event.register(Registries.BLOCK_ENTITY_TYPE, id("@NAME@_home"),
                () -> BlockEntityType.Builder.of(@PASCAL@HomeBlockEntity::new, BLOCK.get()).build(null));
        event.register(Registries.STRUCTURE_TYPE, id("@NAME@_home"),
                () -> (StructureType<@PASCAL@HomeStructure>) () -> @PASCAL@HomeStructure.CODEC);
        event.register(Registries.STRUCTURE_PIECE, id("@NAME@_home_piece"),
                () -> (StructurePieceType.StructureTemplateType) @PASCAL@HomePiece::new);
    }

    @SubscribeEvent
    public static void creativeTabs(BuildCreativeModeTabContentsEvent event) {
        if (event.getTabKey() == CreativeModeTabs.FUNCTIONAL_BLOCKS) {
            event.accept(ITEM.get());
        }
    }
}
