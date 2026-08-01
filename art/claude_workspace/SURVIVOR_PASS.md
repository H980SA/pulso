# Pulso survivor pass

## Accepted derivative

`pulso_disaster_world_survivors_v001.blend`

SHA-256:

`41282ecc37e2b1c77b8d9d7c6a279096c4aa15c2edd8fd9e015b92924223604e`

The file packs all external textures. No absolute unpacked image dependency
remains.

## Review renders

- `renders/survivors/pulso_survivor_A_detection.png`
- `renders/survivors/pulso_survivor_B_detection.png`
- `renders/survivors/pulso_survivors_overview.png`

The overview temporarily hides `VIS_ARCH_CEIL_*` objects only while rendering.
All ceilings are restored and visible in the saved Blender file.

## Validation

- Survivor A wall/ceiling broad-phase: `OK`
- Survivor B wall/ceiling broad-phase: `OK`
- Original collision collection counts remain unchanged:
  - `COLLISION_ARCH`: 46 objects, 276 polygons
  - `COLLISION_DEBRIS_DYNAMIC`: 6 objects, 36 polygons
  - `COLLISION_DEBRIS_STATIC`: 106 objects, 636 polygons
  - `COLLISION_ROVER`: 6 objects, 52 polygons
- Both GLB actors reimported successfully into a clean Blender scene.
- The first body-shell clothing experiment was rejected and is not present in
  the accepted scene.

## Rebuild

Run Blender with the project-local MPFB extension profile and execute:

`scripts/build_pulso_survivors.py`

The script is deterministic and regenerates the actors, semantic metadata,
review cameras, lights, renders, packed Blender derivative, and GLB exports.

## Restore

The immutable source checkpoint remains:

`art/checkpoints/pre_fable_20260730_230714/pulso_disaster_world_pre_fable.blend`

Checkpoint SHA-256:

`c50ecc7bbc0816bda5907ccea4afe3c4caa41e99efbc2c742d6680d6ec0d8205`

To start again, copy the checkpoint to a new writable derivative. Do not edit
the checkpoint in place.
