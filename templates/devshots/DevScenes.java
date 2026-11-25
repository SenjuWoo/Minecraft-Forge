package @PACKAGE@.testing;

import java.util.List;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;

/**
 * The screenshot script of the development client run. This file is yours: add a scene per feature and name its
 * shots {@code <scene>_<what>} so reviews can cite them. The toolkit never overwrites it.
 *
 * <p>Good scenes are deterministic: a NoAI subject, one server-side action per step, fixed camera stations. Measure
 * instead of eyeballing where you can: print {@code DevShots.trace("kind", "key=value ...")} lines from the scene or
 * from dev-flagged mod code and gate them with {@code devlog PROJECT --rules FILE}.
 */
final class DevScenes {
    private DevScenes() {}

    static List<DevShots.Step> build() {
        DevShots.Script s = new DevShots.Script();
        if (DevShots.NORMAL_WORLD) {
            // Real worldgen (verify PROJECT --client --world normal): a normal-terrain world with structures ON.
            // Prove each structure generates, is found quickly, and holds what it should:
            //   s.cmd("gamemode spectator").cmd("time set 6000");
            //   s.locate("minecraft:overworld", "mymod:my_den", 50, 12).snap("locate_den_above");
            //   s.locate("minecraft:the_nether", "mymod:my_shore", 50, 6).snap("locate_shore");
            // Gate it with devlog: {"kind": "locate", "equals": {"found": "1"}, "field": "ms", "max": 5000}.
            // The flat-world scenes below use flat-world coordinates and are skipped here.
            return s.steps;
        }
        // difficulty normal: peaceful deletes hostile subjects and actors. Clear what world generation spawned
        // (slimes, animals), or wild copies of the subject hijack @e[type=...,limit=1] lookups in later scenes.
        s.cmd("difficulty normal").cmd("gamerule doDaylightCycle false").cmd("gamerule doWeatherCycle false").cmd("gamerule doMobSpawning false")
                .cmd("kill @e[type=!minecraft:player]")
                .cmd("weather clear").cmd("time set 6000")
                .cmd("summon " + DevShots.SUBJECT + " 0.5 -60 0.5 {NoAI:1b,PersistenceRequired:1b,Silent:1b,Rotation:[180f,0f]}")
                .cmd("gamemode spectator")
                // `time set` reaches the sky and light a few ticks late, and the entity needs a tick to reach the client
                .waitTicks(50);

        if (DevShots.wanted("turntable")) {
            s.tag("turntable");
            String[] names = {"front", "front_left", "left", "back_left", "back", "back_right", "right", "front_right"};
            for (int i = 0; i < names.length; i++) {
                s.shotFramed("turntable_" + names[i], i * 45f, i % 2 == 0 ? 10f : 15f, 1.0);
            }
            s.shotFramed("turntable_top", 0f, 60f, 1.1);
            s.shotFramed("turntable_close_front", 0f, 5f, 0.6);
        }
        if (DevShots.wanted("uv")) {
            // Orientation proof, once per model: the kit's model swaps in <name>_uvtest.png while mcforge.uvtest is
            // set (a hue per face direction, dark to bright along u, a white band where v starts). Seen from outside,
            // every side face must read dark-left to bright-right with the band on top; guide entities has the rest.
            s.tag("uv").then(4, mc -> System.setProperty("mcforge.uvtest", "true"));
            s.shotFramed("uv_front", 0f, 8f, 0.8).shotFramed("uv_left", 90f, 8f, 0.8)
                    .shotFramed("uv_back", 180f, 8f, 0.8).shotFramed("uv_right", 270f, 8f, 0.8);
            // Top and bottom faces: lift the subject and look from straight above and below (both from behind it).
            String sel = "@e[type=" + DevShots.SUBJECT + ",limit=1,sort=nearest]";
            s.cmd("data merge entity " + sel + " {NoGravity:1b}").cmd("tp " + sel + " 0.5 -52 0.5 180 0").waitTicks(20);
            s.shotFramed("uv_above", 180f, 80f, 0.8);
            s.shotFramed("uv_below", 180f, -80f, 0.8);
            s.cmd("tp " + sel + " 0.5 -60 0.5 180 0").cmd("data merge entity " + sel + " {NoGravity:0b}").waitTicks(10);
            s.then(4, mc -> System.setProperty("mcforge.uvtest", "false"));
        }
        if (DevShots.wanted("night")) {
            // Emissive layers, glow masks and translucent parts read differently at night.
            s.tag("night").cmd("time set 18000").waitTicks(40);
            s.shotFramed("night_front", 20f, 10f, 1.0);
            s.shotFramed("night_back", 200f, 10f, 1.0);
            s.cmd("time set 6000").waitTicks(40);
        }
        if (DevShots.named("audio")) {
            // Plays every sound event of the subject's mod once (opt-in: --scenes audio). devlog then fails on a
            // missing file or an unknown event, which a sound that only plays deep in a sequence would otherwise hide
            // until someone reaches it. Every subtitle shows on screen during the run.
            s.tag("audio").cmd("gamerule sendCommandFeedback false").then(10, mc -> mc.options.showSubtitles().set(true));
            String namespace = ResourceLocation.parse(DevShots.SUBJECT).getNamespace();
            BuiltInRegistries.SOUND_EVENT.keySet().stream().filter(id -> id.getNamespace().equals(namespace)).sorted()
                    .forEach(id -> s.cmd("playsound " + id + " neutral @a ~ ~ ~ 0.6 1").waitTicks(6));
            s.cmd("gamerule sendCommandFeedback true");
        }
        // Leave the world as the next scene expects it: undo time, weather and gamerules you changed, and clear
        // the blocks a scene placed (a "world" scene that builds a plot should fill it with air at its end).
        s.tag("none");
        return s.steps;
    }
}
