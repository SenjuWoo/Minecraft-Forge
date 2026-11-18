package @PACKAGE@.testing;

import java.util.List;

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
        s.cmd("gamerule doDaylightCycle false").cmd("gamerule doWeatherCycle false").cmd("gamerule doMobSpawning false")
                .cmd("weather clear").cmd("time set 6000")
                .cmd("summon " + DevShots.SUBJECT + " 0.5 -60 0.5 {NoAI:1b,PersistenceRequired:1b,Silent:1b,Rotation:[180f,0f]}")
                .cmd("gamemode spectator")
                // `time set` reaches the sky and light a few ticks late, and the entity needs a tick to reach the client
                .waitTicks(50);

        if (DevShots.wanted("turntable")) {
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
            s.then(4, mc -> System.setProperty("mcforge.uvtest", "true"));
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
            s.cmd("time set 18000").waitTicks(40);
            s.shotFramed("night_front", 20f, 10f, 1.0);
            s.shotFramed("night_back", 200f, 10f, 1.0);
            s.cmd("time set 6000").waitTicks(40);
        }
        return s.steps;
    }
}
