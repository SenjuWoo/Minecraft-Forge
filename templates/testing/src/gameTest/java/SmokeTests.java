package @PACKAGE@.testing;

import @PACKAGE@.ExampleMod;
import java.util.List;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.crafting.CraftingInput;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

@GameTestHolder(ExampleMod.MODID)
@PrefixGameTestTemplate(false)
public final class SmokeTests {
    @GameTest(template = "empty")
    public static void registeredBlockCanBePlaced(GameTestHelper helper) {
        var block = ExampleMod.EXAMPLE_BLOCK.get();
        var id = ResourceLocation.fromNamespaceAndPath(ExampleMod.MODID, "example_block");
        helper.assertTrue(id.equals(BuiltInRegistries.BLOCK.getKey(block)), "Wrong registry namespace");
        helper.setBlock(1, 1, 1, block);
        helper.assertBlockPresent(block, 1, 1, 1);
        helper.succeed();
    }

    @GameTest(template = "empty")
    public static void generatedRecipeCraftsOnlyTheExpectedInput(GameTestHelper helper) {
        var id = ResourceLocation.fromNamespaceAndPath(ExampleMod.MODID, "example_items_from_block");
        var holder = helper.getLevel().getRecipeManager().byKey(id).orElseThrow();
        helper.assertTrue(holder.value() instanceof CraftingRecipe, "Generated crafting recipe missing");
        var recipe = (CraftingRecipe) holder.value();
        var input = CraftingInput.of(1, 1, List.of(new ItemStack(ExampleMod.EXAMPLE_BLOCK.get())));
        helper.assertTrue(recipe.matches(input, helper.getLevel()), "Example block must match");
        var result = recipe.assemble(input, helper.getLevel().registryAccess());
        helper.assertTrue(result.is(ExampleMod.EXAMPLE_ITEM.get()) && result.getCount() == 9,
                "Expected nine example items");
        var wrong = CraftingInput.of(1, 1, List.of(new ItemStack(Items.DIRT)));
        helper.assertFalse(recipe.matches(wrong, helper.getLevel()), "Dirt must not match");
        helper.succeed();
    }
}
