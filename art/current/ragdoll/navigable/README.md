# Pulso navigable ragdoll scene

This is a reversible navigation-clearance pass derived from the user-approved
canonical checkpoint. The source checkpoint remains unchanged.

## Deliverable

- Scene: `pulso_ragdoll_navigable.blend`
- Source: `../canonical/pulso_ragdoll_canonical.blend`
- Navigation evidence: `navigation_report.json`
- Review renders:
  - `renders/pulso_navigable_A.png`
  - `renders/pulso_navigable_B.png`
  - `renders/pulso_navigable_top.png`
  - `renders/pulso_navigable_routes.png`

## Navigation pass

- The rover spawn is collision-free.
- Conservative swept footprint: `0.43 m` diameter.
- Corridor transition ramp: smooth entry onto the existing heaved slab.
- Room B south ramp:
  - width: `0.58 m`
  - run: `1.30 m`
  - drop: `0.15 m`
  - grade: `11.538%`
  - angle: `6.582°`
  - endpoint vertical lip: `0.0 m`
- Verified route to A:
  - length: `6.701 m`
  - observation standoff: `2.152 m`
- Verified route to B:
  - length: `6.797 m`
  - endpoint: `(8.35, -2.70) m`, beyond the complete ramp
  - observation standoff: `1.498 m`
  - minimum centered ramp margin after footprint inflation: approximately
    `0.065 m`

The deterministic audit uses a `0.05 m` occupancy grid, 150 obstacle
footprints and an inflated rover radius of `0.215 m`.

## Preserved content

- Original canonical file and hash.
- Both victim locations.
- All pose bones: `0` changed.
- Head, torso, legs, injury cue and cameras.
- Primary and secondary entrapment slabs.
- Static-simulator contract: `0` rigid bodies and `0` rigid-body constraints.

Only loose non-entrapment fragments were relocated. They were preserved in the
scene rather than deleted.

## Survivor B clothing correction

The apparent "arm clipping" was isolated by rendering body, pants and polo
separately. The intersecting gray patch came from the pants penetrating the
polo at the right hip. The physical arm pose was therefore left untouched.

A localized weighted displacement offsets 386 polo vertices by at most
`0.012 m`. A camera-space QA ray at the former intersection now hits the polo
at `1.60899 m`, before the pants at `1.61414 m`.

## Reproduce

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b art/current/ragdoll/canonical/pulso_ragdoll_canonical.blend \
  --python scripts/make_pulso_navigable.py

/Applications/Blender.app/Contents/MacOS/Blender \
  -b art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend \
  --python scripts/audit_pulso_navigation.py

/Applications/Blender.app/Contents/MacOS/Blender \
  -b art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend \
  --python scripts/render_pulso_navigation_route.py
```

## SHA-256

- canonical source:
  `c7eb0b4c8fae95e5e1ce4b226e9055f141e3670eee866172102d74f44582beaa`
- navigable blend:
  `511f710b3dde74785358ff1631a6d0f876b73138c826410224a20862b0079b19`
- navigation report:
  `064e07d646a82d4bb7e05fd365a6b062c84fa5dff05acb60cca6f3cb2d239c3f`
- route render:
  `818a305dde1f7fa696b0837bfa9c5b4f628d786563f47a3d635f4f0af292e5eb`

## Residual validation

This pass proves geometric reachability, ramp continuity and conservative
footprint clearance. Powered-wheel torque, tire friction and suspension
behavior still need a dynamic Gazebo/MuJoCo or physical-rover drive test before
claiming full vehicle traversal under real physics.
