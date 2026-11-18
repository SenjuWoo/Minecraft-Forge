"""The sound events of this mob (lib/soundtools.py turns them into sounds.json, subtitles and
gen/<Mob>Sounds.java). An event with no OGG file yet is reported and left out of sounds.json, so the mod never
references a missing sound.

event id -> (subtitle, file stem or glob under assets/<mod>/sounds/, options)
  options: {"stream": True} for music and other long files; {"volume": 0.8}; {"pitch": 1.0};
           {"attenuation_distance": 24}.
Variants are files that share a stem: step_1.ogg, step_2.ogg ... The game picks one at random.

Practice that held up:
- Positional sounds are mono OGG Vorbis; stereo plays at full volume everywhere. A music disc that should fade
  with distance is mono too.
- One event per spoken line when the subtitle must match the words; grouped events for interchangeable cues.
- Level by measurement, not by ear in an editor: trim silence, cap each take at its event's length, level short
  sounds by RMS (loudness normalisation needs seconds of signal), then limit peaks. Check the whole set with
  `minecraft-forge audio-check PROJECT`; report it as unheard until a person has listened.
- Generate into a staging folder and copy finished files into the mod: a running job must never change mod
  sources mid-verify.
"""

EVENTS = {
    # "ambient": ("Sentinel hums", "ambient_*", {}),
    # "hurt": ("Sentinel grunts", "hurt_*", {}),
    # "death": ("Sentinel falls", "death", {}),
    # "step": ("Footsteps", "step_*", {"volume": 0.6}),
}
