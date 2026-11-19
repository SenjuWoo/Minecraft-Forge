"""The sound events of this mob (lib/soundtools.py turns them into sounds.json, subtitles and
gen/<Mob>Sounds.java).

EVENTS are live: each needs its OGG files (`sounds --validate` fails on one without). PLANNED holds the events
still being made: listed in the report, never an error, never in sounds.json. Move an entry from PLANNED to EVENTS
in the same commit that adds its files.

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

PLANNED = {}

EVENTS = {
    # "ambient": ("Sentinel hums", "ambient_*", {}),
    # "hurt": ("Sentinel grunts", "hurt_*", {}),
    # "death": ("Sentinel falls", "death", {}),
    # "step": ("Footsteps", "step_*", {"volume": 0.6}),
}
