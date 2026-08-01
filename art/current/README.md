# Pulso current scene

Latest navigation-ready ragdoll scene:

`ragdoll/navigable/pulso_ragdoll_navigable.blend`

Its source checkpoint, reproducible build, route audit and review renders are
documented in `ragdoll/navigable/README.md`. The accepted canonical ragdoll
checkpoint remains untouched under `ragdoll/canonical/`.

## Earlier survivor scene

Canonical Blender scene:

`pulso_disaster_world_current.blend`

SHA-256:

`00c802d39d09521a91f565efbc46b3a73aeac9db8d2d4f1bf65bc05312592a5f`

## Current survivor layout

- Survivor A is supine, with the head turned and one arm signaling.
- Survivor B is side-lying, facing the rover camera.
- Each entrapment slab was dropped with Blender rigid-body physics onto
  collision proxies derived from the posed lower legs.
- The deterministic settle ran through frame 300. Maximum movement during the
  final 20 frames was below `0.000001 m`.
- The settled frame was frozen into static transforms. Temporary rigid bodies,
  guide rails, contact proxies, and the rigid-body world were removed.
- Both slabs have a final measured `0.004 m` safety clearance over the maximum
  evaluated actor surface in their contact footprints.

The scene keeps frame 300 as its saved review frame, but the geometry is
static and ready to be exported as the initial state for Gazebo, Unity, or
another simulator.

## Review renders

- `renders/pulso_survivor_A_detection.png`
- `renders/pulso_survivor_B_detection.png`
- `renders/pulso_survivors_overview.png`

## Simulation exports

- `exports/survivors/pulso_survivor_A.glb`
- `exports/survivors/pulso_survivor_B.glb`

Both GLBs reimport successfully in Blender 5.2:

| Actor | Armatures | Mesh objects | Triangles |
| --- | ---: | ---: | ---: |
| A | 1 | 10 | 48,166 |
| B | 1 | 10 | 54,242 |

Use the GLBs as visual geometry. Use simple boxes/capsules for runtime physics
collision in Gazebo or Unity.

## Validation

- Survivor A wall/ceiling broad phase: `OK`
- Survivor B wall/ceiling broad phase: `OK`
- Residual rigid-body objects: `0`
- Residual temporary `_PHYS_` objects: `0`
- Residual Blender rigid-body world: `none`
- Original environment collision collections match the immutable checkpoint:
  - `COLLISION_ARCH`: 46 objects, 276 polygons
  - `COLLISION_DEBRIS_DYNAMIC`: 6 objects, 36 polygons
  - `COLLISION_DEBRIS_STATIC`: 106 objects, 636 polygons
  - `COLLISION_ROVER`: 6 objects, 52 polygons

## Rebuild

Run `scripts/build_pulso_survivors.py` using the project-local Blender/MPFB
profile. The script rebuilds from the pre-survivor source scene, performs the
physics settle, validates rest and contact, freezes frame 300, packs textures,
exports both actors, and renders the review views.

The immutable rollback checkpoint remains:

`art/checkpoints/pre_fable_20260730_230714/pulso_disaster_world_pre_fable.blend`
