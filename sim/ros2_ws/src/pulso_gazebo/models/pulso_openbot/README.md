# OpenBot visual assets

`body_bottom.stl` and `body_top.stl` come from the official OpenBot repository
at commit `67c3185` and are distributed under the adjacent MIT license. The STL
coordinates are millimetres; Gazebo loads them with a `0.001` scale.

Pulso deliberately keeps low-complexity collision primitives. These meshes are
visual evidence only and must not be used to infer physical collision parity.

The authoritative STLs remain untouched. Gazebo loads the reproducible
`*_visual_lod25.stl` derivatives so its GUI remains responsive, while the world
SDF defines a compound collision envelope for the chassis, phone mount, wheels,
bumper, and phone.

Regenerate the visual LODs with:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --factory-startup --python scripts/optimize_openbot_gazebo_assets.py
```
