package @PACKAGE@.@NAME@.home;

import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.ServerLevelAccessor;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.TemplateStructurePiece;
import net.minecraft.world.level.levelgen.structure.pieces.StructurePieceSerializationContext;
import net.minecraft.world.level.levelgen.structure.templatesystem.BlockIgnoreProcessor;
import net.minecraft.world.level.levelgen.structure.templatesystem.LiquidSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplateManager;

/** One generated template, rotated about its centre. The rotation and pivot are saved so the piece reloads as placed. */
public class @PASCAL@HomePiece extends TemplateStructurePiece {
    public @PASCAL@HomePiece(StructureTemplateManager manager, ResourceLocation template, BlockPos origin, Rotation rotation, BlockPos pivot) {
        super(@PASCAL@HomeContent.PIECE_TYPE.get(), 0, manager, template, template.toString(), settings(rotation, pivot), origin);
    }

    public @PASCAL@HomePiece(StructureTemplateManager manager, CompoundTag tag) {
        super(@PASCAL@HomeContent.PIECE_TYPE.get(), tag, manager,
                location -> settings(Rotation.valueOf(tag.getString("Rot")), new BlockPos(tag.getInt("PX"), 0, tag.getInt("PZ"))));
    }

    private static StructurePlaceSettings settings(Rotation rotation, BlockPos pivot) {
        // IGNORE_WATERLOGGING: without it, template blocks placed into an aquifer become waterlogged
        return new StructurePlaceSettings().setRotation(rotation).setMirror(Mirror.NONE).setRotationPivot(pivot)
                .addProcessor(BlockIgnoreProcessor.STRUCTURE_BLOCK).setLiquidSettings(LiquidSettings.IGNORE_WATERLOGGING);
    }

    @Override
    protected void addAdditionalSaveData(StructurePieceSerializationContext context, CompoundTag tag) {
        super.addAdditionalSaveData(context, tag);
        tag.putString("Rot", placeSettings.getRotation().name());
        tag.putInt("PX", placeSettings.getRotationPivot().getX());
        tag.putInt("PZ", placeSettings.getRotationPivot().getZ());
    }

    @Override
    protected void handleDataMarker(String name, BlockPos pos, ServerLevelAccessor level, RandomSource random, BoundingBox box) {
    }
}
