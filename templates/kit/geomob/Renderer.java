package @PACKAGE@.@NAME@.client;

import @PACKAGE@.@NAME@.@PASCAL@Entity;
import @PACKAGE@.kit.CubePasses;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import java.util.Set;
import javax.annotation.Nullable;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.cache.object.GeoCube;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/** Renderer (toolkit: kit PROJECT geomob @NAME@). Yours to edit. */
public class @PASCAL@Renderer extends GeoEntityRenderer<@PASCAL@Entity> implements CubePasses.Filtered {
    /** Model pixels to blocks: 1 means 16 px per block. Springs and BoneMath need the same value. */
    public static final float SCALE = 1.0f;

    public @PASCAL@Renderer(EntityRendererProvider.Context context) {
        super(context, new @PASCAL@Model());
        withScale(SCALE);
        this.shadowRadius = 0.4f;
        // Layers that share the main bones (shells, glass, outlines, armour):
        // addRenderLayer(new SharedBoneLayer<>(this, geo, texture, RenderType::entityTranslucentCull));
        // Glow, drawn only on the cubes with glowmask texels (the pipeline's `cubes` step writes gen/@PASCAL@Cubes):
        // addRenderLayer(new CubePasses.GlowLayer<>(this, @PASCAL@Cubes.GLOWMASK, e -> @PASCAL@Model.TEXTURE));
        // Overlays (wet, flush, damage) from a GeoRenderLayer's render():
        // CubePasses.redraw(getRenderer(), model, @PASCAL@Cubes.WET, poseStack, bufferSource, entity,
        //         RenderType.entityTranslucent(WET_TEXTURE), partialTick, packedLight, packedOverlay, alpha << 24 | 0xFFFFFF);
        // Fade overlays on level game time, never tickCount: the client's and the server's tickCount differ.
    }

    /** While set, only these cubes are drawn: a selective pass (CubePasses) redraws just the cubes it needs. */
    @Nullable
    private Set<GeoCube> cubeFilter;

    @Override
    public void cubeFilter(@Nullable Set<GeoCube> cubes) {
        this.cubeFilter = cubes;
    }

    @Override
    public void renderCube(PoseStack poseStack, GeoCube cube, VertexConsumer buffer, int packedLight, int packedOverlay, int colour) {
        if (cubeFilter == null || cubeFilter.contains(cube)) {
            super.renderCube(poseStack, cube, buffer, packedLight, packedOverlay, colour);
        }
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
