package @PACKAGE@.@NAME@.home;

import com.mojang.serialization.MapCodec;
import javax.annotation.Nullable;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;

/**
 * The @NAME@'s home: a block whose block entity forms the mob beside it and re-forms it when it is gone
 * (toolkit: kit PROJECT home --mob @NAME@). Yours to edit.
 *
 * <p>Put this block in the structure template instead of the entity. A template entity is created once, cannot
 * come back, and is duplicated by every /place; a home block survives chunk unloads, pack updates and deaths.
 */
public class @PASCAL@HomeBlock extends BaseEntityBlock {
    public static final MapCodec<@PASCAL@HomeBlock> CODEC = simpleCodec(@PASCAL@HomeBlock::new);

    public @PASCAL@HomeBlock(Properties properties) {
        super(properties);
    }

    @Override
    protected MapCodec<? extends BaseEntityBlock> codec() {
        return CODEC;
    }

    @Override
    protected RenderShape getRenderShape(BlockState state) {
        return RenderShape.MODEL;
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new @PASCAL@HomeBlockEntity(pos, state);
    }

    @Nullable
    @Override
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide() ? null : createTickerHelper(type, @PASCAL@HomeContent.BLOCK_ENTITY.get(), @PASCAL@HomeBlockEntity::serverTick);
    }
}
