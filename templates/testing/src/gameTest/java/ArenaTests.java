package @PACKAGE@.testing;

import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.block.Blocks;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/**
 * The 15x7x15 "arena" template for entity and AI tests.
 *
 * <p>GameTestHelper positions are relative to the structure block, and the template is placed one block above it
 * (the structure block's default offset is 0, 1, 0). Relative y = 1 is therefore the smooth-stone floor and a mob
 * stands at y = 2. A mob spawned at y = 1 sits inside the floor and takes suffocation damage until it dies.
 */
@GameTestHolder("@MOD_ID@")
@PrefixGameTestTemplate(false)
public final class ArenaTests {
    /** Centre of the arena, standing on the floor. Spawn mobs here or offset from here. */
    public static final BlockPos STAND = new BlockPos(7, 2, 7);
    /** The floor block under {@link #STAND}. */
    public static final BlockPos FLOOR = STAND.below();

    // Regression guard for the stand height: a 1.4-block-wide mob must stay on the floor, alive and unhurt.
    @GameTest(template = "arena", timeoutTicks = 200)
    public static void largeMobStandsUnhurtOnTheArenaFloor(GameTestHelper helper) {
        helper.assertBlockPresent(Blocks.SMOOTH_STONE, FLOOR);
        var horse = helper.spawnWithNoFreeWill(EntityType.HORSE, STAND);
        // runAfterDelay, not succeedOnTickWhen: the latter fails when its condition already holds before the tick.
        helper.runAfterDelay(100, () -> {
            helper.assertTrue(horse.isAlive(), "The horse died in the arena");
            helper.assertTrue(horse.getHealth() == horse.getMaxHealth(),
                    "The horse was hurt: " + horse.getHealth() + "/" + horse.getMaxHealth());
            double feet = helper.relativeVec(horse.position()).y;
            helper.assertTrue(Math.abs(feet - STAND.getY()) < 0.01, "The horse is not standing on the floor: relative y " + feet);
            helper.succeed();
        });
    }
}
