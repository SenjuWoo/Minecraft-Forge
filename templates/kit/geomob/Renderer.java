package @PACKAGE@.@NAME@.client;

import @PACKAGE@.@NAME@.@PASCAL@Entity;
import javax.annotation.Nullable;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/** Renderer (toolkit: kit PROJECT geomob @NAME@). Yours to edit. */
public class @PASCAL@Renderer extends GeoEntityRenderer<@PASCAL@Entity> {
    /** Model pixels to blocks: 1 means 16 px per block. Springs and BoneMath need the same value. */
    public static final float SCALE = 1.0f;

    public @PASCAL@Renderer(EntityRendererProvider.Context context) {
        super(context, new @PASCAL@Model());
        withScale(SCALE);
        this.shadowRadius = 0.4f;
        // Layers that share the main bones (shells, glass, outlines, armour):
        // addRenderLayer(new SharedBoneLayer<>(this, geo, texture, RenderType::entityTranslucentCull));
        // Glow: addRenderLayer(new AutoGlowingGeoLayer<>(this)) needs <texture>_glowmask.png of the same size
        // with at least one opaque texel for every texture the model can return.
    }

    /** Per-texel cutout covers hair tips, holes and straps; switch to entityTranslucentCull only for partial alpha. */
    @Override
    public RenderType getRenderType(@PASCAL@Entity animatable, ResourceLocation texture, @Nullable MultiBufferSource bufferSource,
                                    float partialTick) {
        return RenderType.entityCutoutNoCull(texture);
    }

    /** The death clip lays the model down; no vanilla side flip on top of it. */
    @Override
    protected float getDeathMaxRotation(@PASCAL@Entity animatable) {
        return 0f;
    }
}
