package @PACKAGE@.testing;

import @PACKAGE@.@NAME@.@PASCAL@Content;
import @PACKAGE@.@NAME@.home.@PASCAL@HomeBlockEntity;
import @PACKAGE@.@NAME@.home.@PASCAL@HomeContent;
import @PACKAGE@.@NAME@.home.@PASCAL@HomeStructure;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.level.NoiseColumn;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.AABB;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/**
 * Server-side proof of the @NAME@'s home (toolkit: kit PROJECT home --mob @NAME@). Yours to extend.
 * Worldgen itself (the structure generates, locate finds it) needs a world with structures on:
 * verify PROJECT --client --world normal with a locate scene.
 */
@GameTestHolder("@MODID@")
@PrefixGameTestTemplate(false)
public final class @PASCAL@HomeTests {
    private static List<Mob> residents(GameTestHelper helper) {
        AABB box = new AABB(helper.absolutePos(ArenaTests.STAND)).inflate(8);
        return helper.getLevel().getEntitiesOfClass(Mob.class, box, mob -> mob.getType() == @PASCAL@Content.TYPE.get());
    }

    // The home forms exactly one resident beside it, tags it with the home position, and a second look does not duplicate it.
    @GameTest(template = "arena", timeoutTicks = 200)
    public static void homeFormsOneResident(GameTestHelper helper) {
        helper.setBlock(ArenaTests.STAND, @PASCAL@HomeContent.BLOCK.get());
        helper.runAfterDelay(60, () -> {
            List<Mob> found = residents(helper);
            helper.assertTrue(found.size() == 1, "expected one resident, found " + found.size());
            BlockPos home = helper.absolutePos(ArenaTests.STAND);
            helper.assertTrue(found.get(0).getPersistentData().getLong(@PASCAL@HomeBlockEntity.HOME_KEY) == home.asLong(),
                    "the resident does not remember its home");
            helper.assertTrue(found.get(0).isPersistenceRequired(), "the resident would despawn");
            helper.succeed();
        });
    }

    // The fluid scanner of the anchored structure type: the surface of open lava, and the air-above rule.
    @GameTest(template = "arena", timeoutTicks = 40)
    public static void fluidScannerFindsOpenSurfaces(GameTestHelper helper) {
        BlockState[] states = new BlockState[16];
        for (int i = 0; i < states.length; i++) {
            states[i] = i < 5 ? Blocks.LAVA.defaultBlockState() : i < 13 ? Blocks.AIR.defaultBlockState() : Blocks.STONE.defaultBlockState();
        }
        NoiseColumn column = new NoiseColumn(-64, states);
        int surface = @PASCAL@HomeStructure.fluidSurface(column, Fluids.LAVA, -64, -50, 6);
        helper.assertTrue(surface == -60, "lava surface " + surface);
        helper.assertTrue(@PASCAL@HomeStructure.fluidSurface(column, Fluids.LAVA, -64, -50, 9) == Integer.MIN_VALUE, "too little air was accepted");
        helper.assertTrue(@PASCAL@HomeStructure.fluidSurface(column, Fluids.WATER, -64, -50, 6) == Integer.MIN_VALUE, "the wrong fluid was accepted");
        helper.succeed();
    }
}
