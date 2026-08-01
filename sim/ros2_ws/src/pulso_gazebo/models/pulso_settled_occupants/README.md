# Pulso settled occupant collisions

This generated model adds physical occupancy for the two accepted survivors
and their 26 collapse-debris pieces. Detailed RGB/depth visuals remain in
`pulso_disaster_scene`; this model intentionally has no duplicate visuals.

The runtime is a settled static checkpoint: 16 compound proxies per survivor
(boxes for pelvis/chest and capsules for the remaining segments) plus one
low-poly collision mesh per debris piece. This preserves the accepted collapse
without re-running an unstable rubble simulation during rover navigation. Mass
and friction from the original Bullet run remain in `manifest.json` as
provenance; mass is inactive while this model is static.

All poses use the accepted Blender world XYZ frame. Include the model at a zero
pose; an include pose would misalign collision and rendering.

Regenerate on macOS with:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --factory-startup \
  --python scripts/export_pulso_settled_colliders.py
```

On Ubuntu, replace the Blender path with `blender`. Validate with:

```bash
ign sdf -k \
  sim/ros2_ws/src/pulso_gazebo/models/pulso_settled_occupants/model.sdf
```

OBJ normals are part of the physics contract. Gazebo Fortress' DART/ODE adapter
can reject or crash on collision meshes whose imported vertices lack matching
normals.
