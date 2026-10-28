package @PACKAGE@.testing;

import @PACKAGE@.ExampleMod;
import java.util.concurrent.CompletableFuture;
import net.minecraft.core.HolderLookup;
import net.minecraft.data.PackOutput;
import net.minecraft.data.recipes.RecipeCategory;
import net.minecraft.data.recipes.RecipeOutput;
import net.minecraft.data.recipes.RecipeProvider;
import net.minecraft.data.recipes.ShapelessRecipeBuilder;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.data.event.GatherDataEvent;

@EventBusSubscriber(modid = TestMod.MODID)
public final class ExampleRecipes extends RecipeProvider {
    public ExampleRecipes(PackOutput output, CompletableFuture<HolderLookup.Provider> registries) {
        super(output, registries);
    }

    @SubscribeEvent
    public static void gatherData(GatherDataEvent event) {
        event.getGenerator().addProvider(event.includeServer(), new ExampleRecipes(
                event.getGenerator().getPackOutput(), event.getLookupProvider()));
    }

    @Override
    protected void buildRecipes(RecipeOutput output) {
        ShapelessRecipeBuilder.shapeless(RecipeCategory.MISC, ExampleMod.EXAMPLE_ITEM.get(), 9)
                .requires(ExampleMod.EXAMPLE_BLOCK.get())
                .unlockedBy("has_example_block", has(ExampleMod.EXAMPLE_BLOCK.get()))
                .save(output, ResourceLocation.fromNamespaceAndPath(ExampleMod.MODID, "example_items_from_block"));
    }
}
