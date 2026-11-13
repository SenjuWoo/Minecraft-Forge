# Sounds, sound effects and voice

Minecraft plays OGG Vorbis. A mod's sounds need three things that must agree: the files, `assets/<mod>/sounds.json`, and registered `SoundEvent`s.

## Wiring (NeoForge 1.21.1)

```java
public static final DeferredRegister<SoundEvent> SOUNDS = DeferredRegister.create(Registries.SOUND_EVENT, MODID);
public static final DeferredHolder<SoundEvent, SoundEvent> SWING = SOUNDS.register("mob.swing",
        () -> SoundEvent.createVariableRangeEvent(ResourceLocation.fromNamespaceAndPath(MODID, "mob.swing")));
```

```json
{ "mob.swing": { "subtitle": "subtitles.<mod>.mob.swing",
                 "sounds": [ { "name": "<mod>:sfx/swing1", "volume": 0.9 }, { "name": "<mod>:sfx/swing2" } ] } }
```

- Event ids in Java and `sounds.json` keys are the same string; file names are `assets/<mod>/sounds/<name>.ogg` without the extension.
- Several files under one event give random variation for free; use 2-4 variants for anything heard often (steps, swings, hits).
- Add every subtitle key to `lang/en_us.json`. Generate `sounds.json` from the same script that writes the OGG files, so the two never drift.
- Positional sounds must be **mono**; stereo files ignore distance attenuation. Music and UI may be stereo (`"stream": true` for long tracks).
- Mob hooks: `getAmbientSound`, `getHurtSound`, `getDeathSound`, `playStepSound`; one-shots with `level.playSound(null, x, y, z, event, source, volume, pitch)` on the server.

## Encoding

```text
ffmpeg -y -i in.wav -ac 1 -ar 44100 -af "afade=t=in:d=0.002,alimiter=limit=0.9:level=false" -c:a libvorbis -q:a 7 out.ogg
```

- Call ffmpeg with an argument list (`subprocess.run([...])`), not through a shell: filter graphs contain `|`, `;` and `,` that shells interpret.
- A 2 ms fade-in removes the click at the start; a limiter stops clipping after mixing. Normalise loudness across the set so the voice is not louder than vanilla mobs.
- Trim silence; keep ambient lines short (1-3 s) because the game may cut or overlap them.

## Original sound effects without samples

Synthesis in Python (numpy/scipy) gives original, licence-clean effects that fit a theme:

| Effect | Recipe |
|---|---|
| Blade draw / sheathe | Band-passed noise sweep plus a few inharmonic metal resonators (modal partials ~1 : 2.7 : 5.4) and a short ring |
| Swing / whoosh | Noise through a band-pass whose centre sweeps up then down over 150-250 ms, amplitude bell curve |
| Footstep | Low thump (sine 60-90 Hz, fast decay) plus filtered noise grain matched to the surface |
| Magic cast / heal | Choir-like pad (sawtooth stack through vowel formants), soft bells, rising shimmer grains, short reverb |
| Fanfare | Brass voices: sawtooth with vibrato and a brightening low-pass envelope, chord stabs, room reverb |

- Seed each variant differently; do not ship the same file under three names.
- Keep reverb short (RT ~1 s, mix < 0.3) or the game's own distance mixing turns it to mush. Never add an echo/comb filter to voice: it reads as cheap.
- Render a preview WAV of every clip and listen, or at least check peak, duration and spectral centroid, before encoding.

## Voice

- Robotic TTS is the most common complaint. Plain single-speaker TTS models read interjections letter by letter (`Hmmm` becomes "H-M-M-M"). Use a dialogue model that understands non-verbal tags (`(laughs)`, `(sighs)`, `(humming)`) and write sounds as those tags, not as spelled words.
- Keep one consistent voice: generate a reference line, audition several seeds, keep the one with the right pitch range and clean speech, then condition every later line on that reference audio and text.
- Generate 2-3 takes per line and score them automatically (duration against text length, median pitch near the reference, no long silences) before a human listens.
- Keep the raw takes and the reference in the asset pipeline so lines can be added later in the same voice; ship only the encoded OGGs.
- Lines per event: ambient 4-6, greet 2-3, attack/cast 2-3 each, hurt 3, death 1-2. Rate-limit ambient chatter in code (`getAmbientSoundInterval`).

## Proving it

`verify` proves the files are packaged; it does not prove they play. In a client run, trigger each event (`/playsound <mod>:<event> neutral @s`) and check the log for `Unable to play unknown soundEvent` or missing-file warnings. Report audio as unverified by ear unless someone listened.
