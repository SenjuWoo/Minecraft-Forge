package @PACKAGE@.@NAME@.client;

import @PACKAGE@.@NAME@.@PASCAL@Entity;
import @PACKAGE@.gen.@PASCAL@Rig;
import @PACKAGE@.kit.SpringBones;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.Mth;
import software.bernie.geckolib.animation.AnimationProcessor;
import software.bernie.geckolib.animation.AnimationState;
import software.bernie.geckolib.cache.object.GeoBone;
import software.bernie.geckolib.constant.DataTickets;
import software.bernie.geckolib.model.GeoModel;
import software.bernie.geckolib.model.data.EntityModelData;

/**
 * Model glue (toolkit: kit PROJECT geomob @NAME@). Yours to edit.
 *
 * <p>{@code setCustomAnimations} runs after the keyframes each frame and drives the procedural bones no clip keys:
 * head look and springs. Bone rotations are radians; write them absolutely from the rest snapshot.
 */
public class @PASCAL@Model extends GeoModel<@PASCAL@Entity> {
    public static final ResourceLocation GEO = ResourceLocation.fromNamespaceAndPath("@MODID@", "geo/entity/@NAME@.geo.json");
    public static final ResourceLocation TEXTURE = ResourceLocation.fromNamespaceAndPath("@MODID@", "textures/entity/@NAME@.png");
    public static final ResourceLocation ANIMATIONS = ResourceLocation.fromNamespaceAndPath("@MODID@", "animations/entity/@NAME@.animation.json");
    /** Development hook: -Dmcforge.uvtest=true swaps in the pipeline's UV test texture for orientation screenshots. */
    private static final ResourceLocation UV_TEST = ResourceLocation.fromNamespaceAndPath("@MODID@", "textures/entity/@NAME@_uvtest.png");

    @Override
    public ResourceLocation getModelResource(@PASCAL@Entity animatable) {
        return GEO;
    }

    @Override
    public ResourceLocation getTextureResource(@PASCAL@Entity animatable) {
        return Boolean.getBoolean("mcforge.uvtest") ? UV_TEST : TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(@PASCAL@Entity animatable) {
        return ANIMATIONS;
    }

    @Override
    public void setCustomAnimations(@PASCAL@Entity entity, long instanceId, AnimationState<@PASCAL@Entity> state) {
        super.setCustomAnimations(entity, instanceId, state);
        AnimationProcessor<@PASCAL@Entity> processor = getAnimationProcessor();
        GeoBone look = processor.getBone(@PASCAL@Rig.LOOK);
        EntityModelData data = state.getData(DataTickets.ENTITY_MODEL_DATA);
        if (look != null && data != null && !entity.isDeadOrDying()) {
            // EntityModelData already carries the sign GeckoLib needs: add it to the rest rotation
            look.setRotX(look.getInitialSnapshot().getRotX() + Mth.clamp(data.headPitch(), -40f, 40f) * Mth.DEG_TO_RAD);
            look.setRotY(look.getInitialSnapshot().getRotY() + Mth.clamp(data.netHeadYaw(), -70f, 70f) * Mth.DEG_TO_RAD);
        }
        if (!(entity.clientState instanceof SpringBones.State)) {
            entity.clientState = new SpringBones.State();
        }
        SpringBones.apply(entity, processor, @PASCAL@Rig.SPRINGS, (SpringBones.State) entity.clientState, state.getPartialTick(),
                @PASCAL@Renderer.SCALE, 1f);
    }
}
