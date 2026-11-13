package @PACKAGE@.testing;

import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** Passes once the server has loaded this mod, its registries and its data pack. Add real assertions beside it. */
@GameTestHolder("@MOD_ID@")
@PrefixGameTestTemplate(false)
public final class LoadSmokeTest {
    @GameTest(template = "empty")
    public static void modLoads(GameTestHelper helper) {
        helper.succeed();
    }
}
