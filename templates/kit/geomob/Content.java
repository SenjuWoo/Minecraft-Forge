package @PACKAGE@.@NAME@;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.common.DeferredSpawnEggItem;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.event.entity.EntityAttributeCreationEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.RegisterEvent;

/** Registration (toolkit: kit PROJECT geomob @NAME@). Self-registering: nothing to add to the mod's main class. */
@EventBusSubscriber(modid = @PASCAL@Content.MOD_ID)
public final class @PASCAL@Content {
    public static final String MOD_ID = "@MODID@";
    public static final DeferredHolder<EntityType<?>, EntityType<@PASCAL@Entity>> TYPE =
            DeferredHolder.create(Registries.ENTITY_TYPE, id("@NAME@"));
    public static final DeferredHolder<Item, Item> SPAWN_EGG = DeferredHolder.create(Registries.ITEM, id("@NAME@_spawn_egg"));

    private @PASCAL@Content() {
    }

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    @SubscribeEvent
    public static void register(RegisterEvent event) {
        // Hitbox in blocks; keep it in step with the model height times the renderer scale.
        event.register(Registries.ENTITY_TYPE, id("@NAME@"), () -> EntityType.Builder.of(@PASCAL@Entity::new, MobCategory.CREATURE)
                .sized(@WIDTH@f, @HEIGHT@f).eyeHeight(@EYE@f).clientTrackingRange(10).build("@NAME@"));
        event.register(Registries.ITEM, id("@NAME@_spawn_egg"), () -> new DeferredSpawnEggItem(TYPE, 0x@EGG_A@, 0x@EGG_B@, new Item.Properties()));
    }

    @SubscribeEvent
    public static void attributes(EntityAttributeCreationEvent event) {
        event.put(TYPE.get(), @PASCAL@Entity.createAttributes().build());
    }

    @SubscribeEvent
    public static void creativeTabs(BuildCreativeModeTabContentsEvent event) {
        if (event.getTabKey() == CreativeModeTabs.SPAWN_EGGS) {
            event.accept(SPAWN_EGG.get());
        }
    }
}
