# Blender-generated meshes

Run `scripts/export_pulso_gazebo_assets.py` and then
`scripts/export_pulso_collada.py` with Blender 5.2. The expected outputs are:

- `pulso_disaster_visual.glb` as a modern interchange / inspection artifact
- `pulso_disaster_visual.dae` as the textured Gazebo Fortress runtime mesh
- `pulso_disaster_visual.obj` and its material file as a geometry/debug fallback
- `pulso_disaster_collision.obj`
- `pulso_blender_export_manifest.json`

The visual export bakes the accepted survivor poses and all evaluated Blender
geometry into one runtime mesh with deduplicated material slots. Gazebo
Fortress predates GLB mesh support, and Blender 5.2 no longer ships a Collada
exporter. The direct Collada exporter therefore writes evaluated world-space
triangles, normals, UVs and named material groups without passing through
Assimp (whose Collada output crashes or corrupts this scene in Fortress).
Runtime textures are capped at 1024 px to stay inside Ogre2's streaming pool
while the packed 2K source images remain untouched in the accepted `.blend`
checkpoint. The collision export uses only named collision collections and
never survivor render meshes.

The direct Collada material bridge preserves diffuse textures and constant
colors. Complex Blender-only shader operations such as triplanar blending or
Hue/Saturation tint chains remain an approximation until their final Base
Color is baked.
