# Pulso simulation

The simulator is a sensor source, not a privileged version of Pulso. Gazebo
owns physics and raw sensors; adapter nodes introduce ARCore-like limitations
and publish the stable topics. Ground truth is scoped under `/pulso/sim/**` and
must never reach the Android agent or production WorldState.

## Packages

- `pulso_description`: robot-independent frame tree and OpenBot geometry.
- `pulso_gazebo`: Fortress world, OpenBot physics, sensors, and bridges.
- `pulso_arcore_emulator`: depth-confidence and VIO degradation adapters.
- `pulso_bringup`: one launch entry point.

Build on Ubuntu after sourcing `infra/ubuntu/pulso-env.sh`:

```bash
cd sim/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch pulso_bringup pulso_sim.launch.py
```

For a remote/headless run:

```bash
cd /mnt/linux-data/pulso/repo
scripts/run_sim.sh headless:=true
```

Then prove both contract and autonomous bootstrap behavior from the Mac:

```bash
node scripts/hil_smoke_test.mjs ws://192.168.18.51:9091
node scripts/hil_bootstrap_frontier_test.mjs ws://192.168.18.51:9091
```

The accepted Blender source is exported with
`scripts/export_pulso_gazebo_assets.py`; generated visual and collision meshes
live inside `pulso_gazebo/models/pulso_disaster_scene/meshes/` so a standard
ROS build carries the exact reviewed scene.
