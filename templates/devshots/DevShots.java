package @PACKAGE@.testing;

import com.mojang.logging.LogUtils;
import java.util.Locale;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.Difficulty;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraft.world.phys.AABB;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.slf4j.Logger;

/**
 * Development-only client screenshot run (toolkit: devshots PROJECT, then verify PROJECT --client).
 *
 * <p>Active only when the client starts with -Dmcforge.devshots=true (the devShots run in build.gradle). It
 * creates a fresh flat creative world, summons the subject with NoAI, takes a turntable of screenshots into
 * run-devshots/screenshots, logs "MCFORGE-DEVSHOTS done COUNT" and quits. It lives in the test source set, so it
 * never reaches the mod JAR. Add scenes by extending STATIONS or the tick script below.
 */
@EventBusSubscriber(modid = TestMod.MODID, value = Dist.CLIENT)
public final class DevShots {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final boolean ENABLED = Boolean.getBoolean("mcforge.devshots");
    private static final String SUBJECT = System.getProperty("mcforge.devshots.subject", "minecraft:pig");
    private static final int TIMEOUT_TICKS = 20 * 60 * 5;
    private static final int FIRST_STATION = 70;
    private static final int STATION_TICKS = 10;

    /** A camera station: yaw offset from the subject's front, pitch above it, distance factor. */
    private record Station(String name, float yaw, float pitch, float distance) {}

    private static final Station[] STATIONS = {
            new Station("front", 0, 10, 1), new Station("front_left", 45, 15, 1), new Station("left", 90, 10, 1),
            new Station("back_left", 135, 15, 1), new Station("back", 180, 10, 1), new Station("back_right", 225, 15, 1),
            new Station("right", 270, 10, 1), new Station("front_right", 315, 15, 1), new Station("top", 0, 60, 1.1f),
            new Station("close_front", 0, 5, 0.6f)};

    private static boolean requested;
    private static int total;   // client ticks since the run started
    private static int tick;    // client ticks since the world was joined
    private static int doneAt = -1;
    private static int shots;
    private static Entity subject;

    private DevShots() {}

    @SubscribeEvent
    public static void onClientTick(ClientTickEvent.Post event) {
        if (!ENABLED) {
            return;
        }
        Minecraft mc = Minecraft.getInstance();
        if (++total > TIMEOUT_TICKS && doneAt < 0) {
            fail(mc, "timeout after " + TIMEOUT_TICKS + " ticks");
            return;
        }
        if (mc.level == null || mc.player == null) {
            if (!requested && mc.screen instanceof TitleScreen title) {
                requested = true;
                String name = "devshots_" + System.currentTimeMillis();
                LevelSettings settings = new LevelSettings(name, GameType.CREATIVE, false, Difficulty.PEACEFUL, true, new GameRules(),
                        WorldDataConfiguration.DEFAULT);
                mc.createWorldOpenFlows().createFreshLevel(name, settings, new WorldOptions(1L, false, false),
                        access -> access.registryOrThrow(Registries.WORLD_PRESET).getHolderOrThrow(WorldPresets.FLAT).value().createWorldDimensions(),
                        title);
            }
            return;
        }
        if (tick == 0) {
            // An unattended window loses focus; without this every frame shows the pause menu.
            mc.options.pauseOnLostFocus = false;
            mc.options.hideGui = true;
        }
        if (mc.screen instanceof PauseScreen) {
            mc.setScreen(null);
        }
        tick++;
        if (tick == 20) {
            for (String command : new String[] {"gamerule doDaylightCycle false", "gamerule doWeatherCycle false",
                    "gamerule doMobSpawning false", "weather clear", "time set 6000",
                    "summon " + SUBJECT + " 0.5 -60 0.5 {NoAI:1b,PersistenceRequired:1b,Silent:1b,Rotation:[180f,0f]}",
                    "gamemode spectator"}) {
                mc.player.connection.sendCommand(command);
            }
        }
        if (tick == FIRST_STATION - 10) {
            // `time set` reaches the sky and light a few ticks late; stations start well after it.
            subject = findSubject(mc);
            if (subject == null) {
                fail(mc, "subject " + SUBJECT + " was not found near the origin");
                return;
            }
        }
        int index = (tick - FIRST_STATION) / STATION_TICKS;
        int phase = (tick - FIRST_STATION) % STATION_TICKS;
        if (tick >= FIRST_STATION && index < STATIONS.length) {
            if (phase == 0) {
                place(mc, STATIONS[index]);
            } else if (phase == 6) {
                String file = "devshots_" + STATIONS[index].name() + ".png";
                Screenshot.grab(mc.gameDirectory, file, mc.getMainRenderTarget(), message -> {});
                shots++;
                LOGGER.info("MCFORGE-DEVSHOTS shot {}", file);
            }
        }
        if (tick == FIRST_STATION + STATIONS.length * STATION_TICKS) {
            doneAt = tick;
        }
        if (doneAt > 0 && tick == doneAt + 40) {
            // Screenshots are written on a worker thread; the wait above lets them land before quitting.
            LOGGER.info("MCFORGE-DEVSHOTS done {} subject={} size={}x{}", shots, SUBJECT, subject.getBbWidth(), subject.getBbHeight());
            mc.stop();
        }
    }

    private static Entity findSubject(Minecraft mc) {
        for (Entity entity : mc.level.getEntities((Entity) null, new AABB(-4, -64, -4, 5, -40, 5), e -> !(e instanceof Player))) {
            if (BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString().equals(SUBJECT)) {
                return entity;
            }
        }
        return null;
    }

    /** Teleport the spectator camera to a station and aim it at the subject's centre. */
    private static void place(Minecraft mc, Station station) {
        double height = subject.getBbHeight();
        double size = Math.max(height, subject.getBbWidth());
        double distance = Math.max(2.2, size * 1.8 + 1.0) * station.distance();
        double cx = subject.getX(), cy = subject.getY() + height / 2, cz = subject.getZ();
        double yaw = Math.toRadians(station.yaw()), pitch = Math.toRadians(station.pitch());
        // The subject faces north (-Z); yaw 90 is its left (west).
        double dx = -Math.sin(yaw) * Math.cos(pitch), dz = -Math.cos(yaw) * Math.cos(pitch), dy = Math.sin(pitch);
        double ex = cx + dx * distance, ey = cy + dy * distance, ez = cz + dz * distance;
        double lookX = cx - ex, lookY = cy - ey, lookZ = cz - ez;
        float cameraYaw = (float) Math.toDegrees(Math.atan2(-lookX, lookZ));
        float cameraPitch = (float) -Math.toDegrees(Math.atan2(lookY, Math.sqrt(lookX * lookX + lookZ * lookZ)));
        // tp places the feet; the spectator's eye is 1.62 blocks above them.
        mc.player.connection.sendCommand(String.format(Locale.ROOT, "tp @s %.3f %.3f %.3f %.2f %.2f",
                ex, ey - 1.62, ez, cameraYaw, cameraPitch));
    }

    private static void fail(Minecraft mc, String reason) {
        LOGGER.error("MCFORGE-DEVSHOTS failed: {}", reason);
        doneAt = Integer.MAX_VALUE;
        mc.stop();
    }
}
