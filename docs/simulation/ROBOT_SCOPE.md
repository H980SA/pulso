# Pulso simulation robot scope

## Included in the first executable world

### OpenBot

OpenBot is the only rover body in the first cut. The visual mesh comes from the
official OpenBot CAD snapshot. The simulation description will use simplified
collision geometry and measured or documented dimensions rather than treating
the render mesh as a physics body.

Its drive model is skid / differential drive: the two left motors form one
side, and the two right motors form the other. Optional physical modules are
represented only when they exist in the selected OpenBot build:

- wheel speed sensors / encoders;
- front ultrasonic range;
- bumper / contact;
- battery voltage;
- front, rear, and status lights;
- the mounted Android phone.

LiDAR is not part of the default OpenBot profile. A research-only LiDAR profile
may exist, but it must remain disabled in demonstrations that claim hardware
parity.

## Deferred: SunFounder Zeus Car

The requested Zeus is the SunFounder Arduino Zeus Car:

<https://docs.sunfounder.com/projects/zeus-car/en/latest/>

Its official repository publishes GPL-3.0 firmware and documents a Mecanum
drive, ESP32-CAM, ultrasonic range, two IR obstacle sensors, an eight-direction
grayscale floor module, QMC6310 compass, and RGB lighting:

<https://github.com/sunfounder/zeus-car>

The repository and official downloads do not contain STL, STEP, OBJ, Blender,
URDF, Xacro, or SDF geometry. No reusable third-party model was found during the
2026-07-30 audit. Per the product decision, Zeus is not reconstructed from
photos and is not included visually in the first world.

Pulso will still keep robot-independent command and sensor contracts. If an
authorized CAD model becomes available, Zeus can later add a Mecanum base
adapter without changing the cognitive layer.

## Separation of responsibilities

- Blender owns visual meshes, materials, UVs, rigs, animations, and low-poly
  collision exports.
- ROS / Gazebo owns mass, inertia, joints, friction, drive plugins, sensors,
  timestamps, noise, and coordinate frames.
- Pulso consumes normalized world observations and emits motion goals. It does
  not depend on whether the carrier is OpenBot, Zeus, a hexapod, or a drone.

