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

- Pitch-match takes instead of regenerating them: give each class a ceiling above the speaking reference (sighs and hums about +3 to +5 semitones, gasps, hurts and shouts up to +10 to +12: non-verbals sit higher and climb with intensity) and shift the best take back inside it with a formant-preserving shifter. Beyond about 6 semitones of shift it sounds processed: rewrite the line and retake it.
- A text-to-speech model that reads tags as words cannot make non-verbals; a dialogue model conditioned on the reference held the pitch on sustained non-verbals (+0.9 semitones). Keep the reference and the scorer's table (`SCORES.md`) in the pipeline.

## Post-processing and staging (`build_assets.py audio`)

Generators write into `asset-pipeline/audio/export/<class>/` (voice, sfx, music), never into the mod. `audio export` writes the processed set into `assets/<mod>/sounds/<mob>/`: 35 Hz high-pass, silence trimmed, RMS levelling (voice -24 dB, effects -22 dB; `mob/sounds.py` AUDIO overrides per class), a soft limiter under -1 dBFS, mono Vorbis (music too: a positional disc in stereo is heard across the world). Only changed files are rewritten. `audio --validate` fails on silent, clipping, sub-50 ms or non-mono files and on variants that are copies (correlation above 0.98).

- Generators have returned the same audio for every same-text variant of one batch. Run one variant index per run with its own seed, and let the validator (and `audio-check`, which flags identical variants of an event) catch copies.
- A take that comes back silent gets its own reseed instead of a rerun of the batch.
- Effects levelled to one RMS level narrowed a set from a -38..-5 dB spread to -29..-13 dB.
- Never generate audio while a game client runs on the same GPU, and never let a generator write into the mod while `verify` runs.
- Events whose files are still being made go in `mob/sounds.py` PLANNED: reported, never an error, never in `sounds.json`. Move them to EVENTS with their files.
- `verify --client --scenes audio` plays every sound event of the mod once (the DevScenes `audio` scene, opt-in); `devlog` then fails on a missing file or unknown event that only a late sequence step would play.

## Checking the set (`audio-check`)

`audio-check PROJECT` reports in one go: `sounds.json` events against `SoundEvent` ids registered in Java (a source scan of `DeferredHolder<SoundEvent, ...>`, `SOUNDS.register("id", ...)` and `SoundEvent.createVariableRangeEvent(...)` / `SoundEvent.of(...)` patterns), entries whose `.ogg` is missing, files nobody references, missing subtitle keys, and per file: channels (positional sounds must be mono), sample rate, duration (long sounds should set `"stream": true`) and, with FFmpeg on PATH, mean and peak loudness. Variants of one event that are the same audio (same bytes, or with FFmpeg the same decoded samples) are a problem. It exits 1 on problems (a registered event without a `sounds.json` entry plays nothing).

- Generating many takes locally: check that no other job holds the GPU first (`nvidia-smi`). A text-to-sound job slowed from about 17 s to 5 minutes per take while another session's job shared the GPU.
- Voice consistency: derive variants (hurt, panic, death) from a few base takes by pitch and time processing instead of generating each separately.
- Loudness-match the set by RMS with a limiter; `audio-check` warns when mean loudness spans more than 9 dB. Loudness normalisation (`loudnorm`) needs about three seconds of signal: on sub-second effects it gave a 24 dB spread and overshot voice by 4 LU. Trim padding silence, cap each take at its event's length, apply one static gain per file from measured RMS, then limit peaks (about -1.5 dBTP).
- High-pass effects at about 35 Hz before levelling: generated takes can carry sub-20 Hz rumble that eats the level (one read -19 LUFS but -5 dB RMS). Loudness meters cannot measure files under about 0.4 s; pad to 0.5 s for the measurement only.
- A dialogue model conditioned on a reference voice does not hold its pitch for non-verbal sounds (takes landed 200-350 Hz against a 168 Hz voice): shift each take to a per-kind target with a formant-preserving pitch shifter instead of regenerating until one matches.
- Music generators return less than asked: a 10 s request gave 6-7 s. Request about twice the length, trim, and write the real length into the jukebox data.
- Keep one source for events, subtitles and generated ids. An exporter that writes its own `sounds.json` beside yours gives two sources that drift.
- Targets measured from vanilla 1.21.1 sounds: voice about -24 dB mean, foley -26, soft ambience -27, hits -20.
- Cut reaction sounds to their animation (a hurt grunt under a second); a sound longer than its clip trails into the next action.
- Pick takes by measurement: score real voicing (a dialogue model sometimes renders a whistle or drone instead of a voice and its own ranking does not notice), pitch against the reference and a speech-to-text match of the words; non-verbal takes fail the word check by design.
- One sound event per spoken line when a subtitle must show exactly those words, with the recorded length in ticks as a generated constant (talk time, queues); grouped events with variants for interchangeable cues.
- A music disc that should fade with distance is mono, like every positional sound; `JukeboxSong.length_in_seconds` is the real length of the take, not the one requested.
- Generate into a staging folder outside the mod and copy finished sets in: a running generation job must never change mod sources while `verify` hashes its inputs.

## Proving it

`verify` proves the files are packaged; it does not prove they play. In a client run, trigger each event (`/playsound <mod>:<event> neutral @s`) and check the log for `Unable to play unknown soundEvent` or missing-file warnings. Report audio as unverified by ear unless someone listened.
