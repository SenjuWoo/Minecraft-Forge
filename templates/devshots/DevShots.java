package @PACKAGE@.testing;

import com.mojang.logging.LogUtils;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.screens.AccessibilityOnboardingScreen;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.Difficulty;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.slf4j.Logger;

/**
 * Development-only client screenshot run (toolkit: devshots PROJECT, then verify PROJECT --client).
 *
 * <p>Active only when the client starts with -Dmcforge.devshots=true (the devShots run in build.gradle). It creates a
 * fresh flat creative world and plays the script built by {@link DevScenes}: commands, camera stations, screenshots,
 * waits and server-side actions, one step at a time. It then logs "MCFORGE-DEVSHOTS done COUNT" and quits. It lives
 * in the test source set, so it never reaches the mod JAR.
 *
 * <p>This file is the engine and is replaced by {@code devshots PROJECT --force}; scenes belong in DevScenes.java,
 * which the toolkit never overwrites. Limit a run to named scenes with {@code verify PROJECT --client --scenes a,b}
 * (it writes run-devshots/scenes.txt) or -Dmcforge.devshots.scenes=a,b.
 *
 * <p>The world: flat, creative, structures off by default (fast, and nothing wanders into the shots). Real worldgen
 * needs {@code verify PROJECT --client --world normal} (it writes run-devshots/world.txt; -Dmcforge.devshots.world
 * does the same): a normal-terrain world with structure generation ON. With structures off, a structure's
 * placement check still passes but no start is ever generated, and a locate search runs for minutes and finds
 * nothing. In a normal world the flat-world coordinates of the starter scenes do not apply: see NORMAL_WORLD.
 *
 * <p>Do not click or focus the game window during a run: the client then stops following the camera teleports and
 * every later frame is the same picture (the receipt warns about identical consecutive frames).
 */
@EventBusSubscriber(modid = TestMod.MODID, value = Dist.CLIENT)
public final class DevShots {
    static final Logger LOGGER = LogUtils.getLogger();
    private static final boolean ENABLED = Boolean.getBoolean("mcforge.devshots");
    static final String SUBJECT = System.getProperty("mcforge.devshots.subject", "minecraft:pig");
    private static final int TIMEOUT_TICKS = Integer.getInteger("mcforge.devshots.timeout", 20 * 60 * 20);
    private static final String WORLD = worldSetting();
    /** True in a normal-terrain world with structures (world setting "normal"); false in the flat test world. */
    static final boolean NORMAL_WORLD = WORLD.startsWith("normal");
    private static final long SEED = Long.getLong("mcforge.devshots.seed", 1L);
    private static final Map<String, BlockPos> LOCATED = new ConcurrentHashMap<>();

    /** One scripted step: an action, then {@code delay} client ticks of waiting (0 = the next step runs next tick). */
    record Step(int delay, Consumer<Minecraft> action) {}

    private static boolean requested;
    private static int total;
    private static int tick;
    private static int shots;
    private static int stepIndex;
    private static int waitLeft;
    private static int quitIn = -1;
    private static boolean finished;
    private static List<Step> script;
    private static String scenes;
    static Entity subject;

    private DevShots() {}

    @SubscribeEvent
    public static void onClientTick(ClientTickEvent.Post event) {
        if (!ENABLED || finished) {
            return;
        }
        Minecraft mc = Minecraft.getInstance();
        if (++total > TIMEOUT_TICKS && quitIn < 0) {
            fail(mc, "timeout after " + TIMEOUT_TICKS + " ticks at step " + stepIndex);
            return;
        }
        if (mc.level == null || mc.player == null) {
            if (mc.screen instanceof AccessibilityOnboardingScreen) {
                // A new game directory opens this screen before the title screen; the run would wait forever.
                mc.options.onboardAccessibility = false;
                mc.options.save();
                mc.setScreen(new TitleScreen());
                return;
            }
            if (!requested && mc.screen instanceof TitleScreen title) {
                requested = true;
                String name = "devshots_" + System.currentTimeMillis();
                LevelSettings settings = new LevelSettings(name, GameType.CREATIVE, false, Difficulty.PEACEFUL, true, new GameRules(),
                        WorldDataConfiguration.DEFAULT);
                // second argument: generate structures. Off in the flat world; it must be on to prove worldgen.
                mc.createWorldOpenFlows().createFreshLevel(name, settings, new WorldOptions(SEED, NORMAL_WORLD, false),
                        access -> access.registryOrThrow(Registries.WORLD_PRESET)
                                .getHolderOrThrow(NORMAL_WORLD ? WorldPresets.NORMAL : WorldPresets.FLAT).value().createWorldDimensions(),
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
        if (quitIn >= 0) {
            // Screenshots are written on a worker thread; the wait lets them land before quitting.
            if (quitIn-- == 0) {
                finished = true;
                LOGGER.info("MCFORGE-DEVSHOTS done {} subject={} scenes={}", shots, SUBJECT, scenesFilter().isBlank() ? "all" : scenesFilter());
                mc.stop();
            }
            return;
        }
        if (tick < 20) {
            return;
        }
        if (script == null) {
            script = DevScenes.build();
            LOGGER.info("MCFORGE-DEVSHOTS script steps={}", script.size());
        }
        if (waitLeft > 0) {
            waitLeft--;
            return;
        }
        if (stepIndex < script.size()) {
            Step step = script.get(stepIndex++);
            try {
                step.action().accept(mc);
            } catch (RuntimeException error) {
                LOGGER.error("MCFORGE-DEVSHOTS step failed", error);
                fail(mc, "step " + (stepIndex - 1) + " threw " + error);
                return;
            }
            waitLeft = step.delay();
        } else {
            quitIn = 40;
        }
    }

    // ------------------------------------------------------------------ helpers for DevScenes

    /** True when the scene is wanted: no filter, or the scene is named in it. */
    static boolean wanted(String scene) {
        String only = scenesFilter();
        if (only.isBlank()) {
            return true;
        }
        for (String name : only.split(",")) {
            if (name.trim().equals(scene)) {
                return true;
            }
        }
        return false;
    }

    private static String scenesFilter() {
        if (scenes == null) {
            scenes = System.getProperty("mcforge.devshots.scenes", "");
            Path file = Minecraft.getInstance().gameDirectory.toPath().resolve("scenes.txt");
            if (scenes.isBlank() && Files.exists(file)) {
                try {
                    scenes = Files.readString(file).trim();
                } catch (IOException ignored) {
                    scenes = "";
                }
            }
        }
        return scenes;
    }

    private static String worldSetting() {
        String value = System.getProperty("mcforge.devshots.world", "");
        Path file = Path.of("world.txt");   // the game directory is the working directory of the run
        if (value.isBlank() && Files.exists(file)) {
            try {
                value = Files.readString(file).trim();
            } catch (IOException ignored) {
                value = "";
            }
        }
        return value.isBlank() ? "flat" : value.toLowerCase(Locale.ROOT);
    }

    /**
     * Search for the nearest start of a structure on the server, bounded to {@code radiusChunks} placement cells
     * around the origin, and log {@code MCFORGE-TRACE locate structure=ID found=0|1 x= y= z= ms=} for devlog. An
     * unbounded search stalls a server where no structure is near; so does any item or command built on one.
     */
    static void locate(Minecraft mc, String dimension, String structureId, int radiusChunks) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) {
            return;
        }
        server.execute(() -> {
            ServerLevel level = server.getLevel(ResourceKey.create(Registries.DIMENSION, ResourceLocation.parse(dimension)));
            Holder<Structure> holder = level.registryAccess().registryOrThrow(Registries.STRUCTURE)
                    .getHolderOrThrow(ResourceKey.create(Registries.STRUCTURE, ResourceLocation.parse(structureId)));
            long start = System.nanoTime();
            var found = level.getChunkSource().getGenerator().findNearestMapStructure(level, HolderSet.direct(holder), BlockPos.ZERO,
                    radiusChunks, false);
            long ms = (System.nanoTime() - start) / 1_000_000;
            if (found == null) {
                trace("locate", "structure=" + structureId + " found=0 ms=" + ms);
            } else {
                BlockPos pos = found.getFirst();
                LOCATED.put(structureId, pos);
                trace("locate", String.format(Locale.ROOT, "structure=%s found=1 x=%d y=%d z=%d ms=%d", structureId, pos.getX(), pos.getY(), pos.getZ(), ms));
            }
        });
    }

    /** Where {@link #locate} found the structure (the start position; y is not the floor), or null. */
    static BlockPos located(String structureId) {
        return LOCATED.get(structureId);
    }

    /** A machine-readable line for {@code devlog PROJECT}: {@code MCFORGE-TRACE kind key=value key=value}. */
    static void trace(String kind, String fields) {
        LOGGER.info("MCFORGE-TRACE {} {}", kind, fields);
    }

    static void cmd(Minecraft mc, String command) {
        mc.player.connection.sendCommand(command);
    }

    /** Name: lowercase letters, digits and underscores (the receipt records devshots_NAME.png). */
    static void shot(Minecraft mc, String name) {
        String file = "devshots_" + name.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_]", "_") + ".png";
        Screenshot.grab(mc.gameDirectory, file, mc.getMainRenderTarget(), message -> {});
        shots++;
        LOGGER.info("MCFORGE-DEVSHOTS shot {}", file);
    }

    static String typeId(Entity entity) {
        return BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString();
    }

    /** The client-side subject nearest the world origin column, or null. */
    static Entity findSubject(Minecraft mc) {
        Entity best = null;
        double bestDistance = Double.MAX_VALUE;
        for (Entity entity : mc.level.entitiesForRendering()) {
            if (typeId(entity).equals(SUBJECT)) {
                double d = entity.getX() * entity.getX() + entity.getZ() * entity.getZ();
                if (d < bestDistance) {
                    bestDistance = d;
                    best = entity;
                }
            }
        }
        return best;
    }

    private static Entity needSubject(Minecraft mc) {
        if (subject == null || subject.isRemoved()) {
            subject = findSubject(mc);
        }
        if (subject == null) {
            throw new IllegalStateException("subject " + SUBJECT + " was not found");
        }
        return subject;
    }

    /**
     * Teleport the spectator camera around the subject and aim it at a point {@code aimY} blocks above its feet.
     * Yaw is measured from the subject's front when it faces north (-Z): 90 is its left, 180 its back.
     */
    static void place(Minecraft mc, float yawDeg, float pitchDeg, double distance, double aimY) {
        Entity s = needSubject(mc);
        double cx = s.getX(), cy = s.getY() + aimY, cz = s.getZ();
        double yaw = Math.toRadians(yawDeg), pitch = Math.toRadians(pitchDeg);
        double dx = -Math.sin(yaw) * Math.cos(pitch), dz = -Math.cos(yaw) * Math.cos(pitch), dy = Math.sin(pitch);
        double ex = cx + dx * distance, ey = cy + dy * distance, ez = cz + dz * distance;
        double lookX = cx - ex, lookY = cy - ey, lookZ = cz - ez;
        float cameraYaw = (float) Math.toDegrees(Math.atan2(-lookX, lookZ));
        float cameraPitch = (float) -Math.toDegrees(Math.atan2(lookY, Math.sqrt(lookX * lookX + lookZ * lookZ)));
        // tp places the feet; the spectator's eye is 1.62 blocks above them.
        cmd(mc, String.format(Locale.ROOT, "tp @s %.3f %.3f %.3f %.2f %.2f", ex, ey - 1.62, ez, cameraYaw, cameraPitch));
    }

    /** {@link #place} with the distance and aim height taken from the subject's hitbox (factor 1 frames all of it). */
    static void frame(Minecraft mc, float yawDeg, float pitchDeg, double factor) {
        Entity s = needSubject(mc);
        double size = Math.max(s.getBbHeight(), s.getBbWidth());
        place(mc, yawDeg, pitchDeg, Math.max(2.2, size * 1.8 + 1.0) * factor, s.getBbHeight() / 2);
    }

    /** Run an action on the integrated server thread for every server-side entity of the subject's type. */
    static void onServer(Minecraft mc, Consumer<Entity> action) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) {
            return;
        }
        server.execute(() -> {
            for (Entity entity : server.overworld().getAllEntities()) {
                if (typeId(entity).equals(SUBJECT)) {
                    action.accept(entity);
                }
            }
        });
    }

    static void fail(Minecraft mc, String reason) {
        LOGGER.error("MCFORGE-DEVSHOTS failed: {}", reason);
        finished = true;
        mc.stop();
    }

    /** Small builder for scripts. */
    static final class Script {
        final List<Step> steps = new ArrayList<>();

        /** Run the action, then wait {@code wait} ticks. */
        Script then(int wait, Consumer<Minecraft> action) {
            steps.add(new Step(wait, action));
            return this;
        }

        Script cmd(String command) {
            return then(1, mc -> DevShots.cmd(mc, command));
        }

        /**
         * Label the trace lines that follow ({@code MCFORGE-TRACE ... id=<name>}) so devlog rules and spring tuning
         * can pick one scene; "none" ends the label.
         */
        Script tag(String name) {
            return then(1, mc -> System.setProperty("mcforge.trace.tag", name));
        }

        Script waitTicks(int ticks) {
            return then(ticks, mc -> {});
        }

        /** Move the camera, let the frame settle, take the screenshot. */
        Script shotAt(String name, float yaw, float pitch, double distance, double aimY) {
            then(5, mc -> place(mc, yaw, pitch, distance, aimY));
            return then(3, mc -> shot(mc, name));
        }

        /** As {@link #shotAt} with the camera distance derived from the subject's hitbox. */
        Script shotFramed(String name, float yaw, float pitch, double factor) {
            then(5, mc -> frame(mc, yaw, pitch, factor));
            return then(3, mc -> shot(mc, name));
        }

        /** Locate a structure (bounded), then fly the spectator camera above it: 200 ticks let the chunks generate. */
        Script locate(String dimension, String structureId, int radiusChunks, int heightAbove) {
            then(20, mc -> DevShots.locate(mc, dimension, structureId, radiusChunks));
            return then(200, mc -> {
                BlockPos pos = located(structureId);
                if (pos == null) {
                    throw new IllegalStateException(structureId + " was not found within " + radiusChunks + " placement cells");
                }
                DevShots.cmd(mc, String.format(Locale.ROOT, "execute in %s run tp @s %d %d %d 0 60", dimension, pos.getX(), pos.getY() + heightAbove, pos.getZ()));
            });
        }

        /** Take a screenshot from where the camera is. */
        Script snap(String name) {
            return then(3, mc -> DevShots.shot(mc, name));
        }

        /** Run a server-side action on the subject, then wait. */
        Script server(int wait, Consumer<Entity> action) {
            return then(wait, mc -> onServer(mc, action));
        }

        /**
         * Start something on the server and shoot at the given tick offsets after it (ascending, each at least 1).
         * A step's action runs and then waits {@code delay} ticks, so a delay of n puts the next step n + 1 ticks later.
         */
        Script burst(String name, Consumer<Entity> start, int... frames) {
            then(frames[0] - 1, mc -> onServer(mc, start));
            for (int i = 0; i < frames.length; i++) {
                int frame = frames[i];
                int next = i + 1 < frames.length ? frames[i + 1] - frame - 1 : 10;
                then(next, mc -> shot(mc, name + "_" + frame));
            }
            return this;
        }
    }
}
