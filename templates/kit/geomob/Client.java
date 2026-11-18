package @PACKAGE@.@NAME@.client;

import @PACKAGE@.@NAME@.@PASCAL@Content;
import @PACKAGE@.@NAME@.@PASCAL@Entity;
import @PACKAGE@.kit.SpringBones;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;

/** Client registration (toolkit: kit PROJECT geomob @NAME@). Client side only. */
@EventBusSubscriber(modid = @PASCAL@Content.MOD_ID, value = Dist.CLIENT)
public final class @PASCAL@Client {
    private @PASCAL@Client() {
    }

    @SubscribeEvent
    public static void renderers(EntityRenderersEvent.RegisterRenderers event) {
        event.registerEntityRenderer(@PASCAL@Content.TYPE.get(), @PASCAL@Renderer::new);
        // Animation timeline events reach the client here: a footfall nudges the springs on the exact frame.
        @PASCAL@Entity.instructionSink = @PASCAL@Client::onInstructions;
    }

    private static void onInstructions(@PASCAL@Entity entity, String instructions) {
        if (!(entity.clientState instanceof SpringBones.State state)) {
            return;
        }
        for (String part : instructions.split(";")) {
            String name = part.trim();
            int hash = name.indexOf('#');
            if (hash >= 0) {
                name = name.substring(0, hash);
            }
            if (name.startsWith("step")) {
                SpringBones.kick(state, "", 0f, -6f, 0f);
            }
        }
    }
}
