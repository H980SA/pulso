# Pulso simulated phone and rover sensor contract

## Purpose

The simulator must expose the same useful observations that the Android
application and physical rover can expose. It must not give Pulso privileged
ground-truth data or sensors that the demonstrated hardware does not own.

Gazebo produces physical sensor samples. Adapter nodes transform those samples
into this stable contract. The Android implementation will publish the same
contract, allowing the cognitive layer to switch between simulation and the
Samsung phone without changing its logic.

## Coordinate frames

The minimum transform tree is:

```text
map
└── odom
    └── base_link
        ├── base_footprint
        ├── phone_mount
        │   ├── phone_imu_link
        │   └── phone_camera_link
        │       └── phone_camera_optical_frame
        ├── sonar_front_link
        └── bumper_link
```

All image, depth, point, IMU, odometry, and transform messages use a common
simulation clock and valid frame IDs.

## Stable ROS 2 topics

| Observation | Topic | ROS 2 type | Notes |
| --- | --- | --- | --- |
| RGB image | `/pulso/phone/rgb/image` | `sensor_msgs/msg/Image` | Configurable resolution and rate |
| RGB JPEG | `/pulso/phone/rgb/compressed` | `sensor_msgs/msg/CompressedImage` | Bounded HIL transfer to Android |
| RGB calibration | `/pulso/phone/rgb/camera_info` | `sensor_msgs/msg/CameraInfo` | Intrinsics match rendered camera |
| Raw depth | `/pulso/phone/depth/raw` | `sensor_msgs/msg/Image` | `16UC1`, millimetres; zero means unavailable |
| Smoothed depth | `/pulso/phone/depth/smoothed` | `sensor_msgs/msg/Image` | Dense but less trustworthy |
| Raw-depth confidence | `/pulso/phone/depth/confidence` | `sensor_msgs/msg/Image` | `mono8`, 0–255 |
| Dense depth cloud | `/pulso/phone/depth/points` | `sensor_msgs/msg/PointCloud2` | Derived from depth and intrinsics |
| Sparse AR feature cloud | `/pulso/phone/arcore/feature_points` | `sensor_msgs/msg/PointCloud2` | Fields include XYZ, confidence, and point ID |
| Raw phone IMU | `/pulso/phone/imu/data_raw` | `sensor_msgs/msg/Imu` | Angular velocity and linear acceleration |
| VIO estimate | `/pulso/phone/vio/odom` | `nav_msgs/msg/Odometry` | Noisy, drifting estimate; never ground truth |
| Tracking quality | `/pulso/phone/vio/status` | `diagnostic_msgs/msg/DiagnosticArray` | `TRACKING`, `LIMITED`, or `LOST` plus cause |
| Sonar | `/pulso/base/sonar/front` | `sensor_msgs/msg/Range` | Only in the matching OpenBot profile |
| Wheel odometry | `/pulso/base/wheel/odom` | `nav_msgs/msg/Odometry` | Encoder-derived, with slip |
| Bumper | `/pulso/base/bumper` | `std_msgs/msg/Bool` | Contact fail-safe |
| Battery | `/pulso/base/battery` | `sensor_msgs/msg/BatteryState` | Simulated discharge and low-battery state |
| Flashlight command | `/pulso/phone/flashlight/cmd` | `std_msgs/msg/Bool` | Agent-controllable |
| Flashlight state | `/pulso/phone/flashlight/state` | `std_msgs/msg/Bool` | Confirmed actuator state |
| Navigation candidates | `/pulso/navigation/candidates` | `std_msgs/msg/String` | Versioned typed IDs and validity |
| MetaView | `/pulso/navigation/metaview/compressed` | `sensor_msgs/msg/CompressedImage` | Demand-only map evidence for Gemma |
| Interactive MetaView scene | `/pulso/navigation/metaview_scene` | `std_msgs/msg/String` | `pulso.metaview-scene.v1`: live 2.5D occupancy, transformed depth points, rover and candidate routes in `map` |
| HIL observation | `/pulso/hil/observation` | `std_msgs/msg/String` | `pulso.observation.v1` envelope |
| HIL perception tracks | `/pulso/hil/perception_tracks` | `std_msgs/msg/String` | Short-lived phone saliency clues |
| Action intent/result | `/pulso/hil/action_intent`, `/pulso/hil/action_result` | `std_msgs/msg/String` | Typed guarded action contract |
| Public brain trace | `/pulso/hil/brain_trace` | `std_msgs/msg/String` | `pulso.brain-trace.v1`; bounded causal events, never private model reasoning |
| Exact Gemma input evidence | `/pulso/hil/gemma_input` | `std_msgs/msg/String` | `pulso.gemma-input.v1`; exact message and harness metadata for one real turn |
| Exact Gemma image evidence | `/pulso/hil/gemma_view/compressed` | `sensor_msgs/msg/CompressedImage` | Same JPEG bytes attached to Gemma, joined to `gemma_input` by SHA-256 |
| Perception runtime telemetry | `/pulso/hil/perception_telemetry` | `std_msgs/msg/String` | `pulso.perception-telemetry.v1`; model ID, optional provider, health, timing and detection count |

The exact namespace may later be remapped per robot. Message meaning and frame
conventions must remain stable.

### MetaView scene semantics

`/pulso/navigation/metaview_scene` is an operator visualization derived only
from live robot-accessible evidence. Its occupancy points come from `/map`, its
3D points come from phone depth transformed into `map`, and its routes come
from the current navigation revision. Unknown occupancy cells are omitted. The
occupancy layer is 2.5D for legibility; only depth points carry measured Z.

This stream is not the image supplied to Gemma and it must never contain the
Blender mesh, survivor labels or other simulator ground truth. The
demand-driven 2D MetaView JPEG remains
`/pulso/navigation/metaview/compressed`.

### Auditable model-call semantics

When a real Gemma runtime is active it publishes one
`pulso.gemma-input.v1` record before inference. The record includes the exact
text/order, model and world/turn identity, system prompt, tool schemas,
conversation scope and hashes. An attached JPEG is not duplicated as Base64 in
that JSON. Its exact bytes travel once on
`/pulso/hil/gemma_view/compressed`; the SHA-256 and byte count join both
records.

`/pulso/hil/brain_trace` is safe-to-show causal telemetry such as WorldPacket
selection, model input, tool request, tool result and cycle completion. It is
not chain-of-thought. The browser must display missing or stale topics as such;
it must not synthesize live evidence.

## ARCore-equivalent behaviour

Gazebo's RGB-D output is too clean to represent ARCore. The
`pulso_arcore_emulator` adapter will therefore publish two different clouds:

1. a dense point cloud reconstructed from the emulated depth image;
2. a sparse feature-point cloud corresponding to ARCore's tracked visual
   features.

The emulation profile must include:

- synchronized RGB, depth, confidence, pose, and timestamps;
- startup warm-up before depth becomes valid;
- missing raw-depth pixels rather than a perfect dense image;
- confidence that decreases on textureless, reflective, distant, and
  grazing-angle surfaces;
- best depth behaviour in the approximate 0.5–5 m working region;
- noise that increases with range;
- depth frames that may be stale / reprojected instead of newly measured;
- motion blur, exposure changes, darkness, and camera occlusion;
- IMU bias, white noise, sampling jitter, and dropped samples;
- VIO drift, relocalization, and explicit limited / lost tracking;
- no use of simulator ground truth outside the noise-model node and benchmark
  evaluator.

Default development rates are deliberately modest and configurable:

- RGB: 640×480 at 30 Hz;
- raw and smoothed depth: 15 Hz;
- dense cloud: 10–15 Hz;
- sparse feature cloud: 15–30 Hz;
- IMU: 100 Hz;
- VIO pose: 30 Hz.

These are performance-test defaults, not claims about a fixed ARCore output
resolution. Final intrinsics, rates, and latency will be calibrated from the
Samsung S25 Ultra.

## OpenBot simulation profile

The first OpenBot profile contains:

- four physical wheel links with left/right differential control;
- wheel-ground slip and rubble-dependent friction;
- optional encoder ticks converted to wheel odometry;
- one front ultrasonic range sensor with minimum range, maximum range,
  quantization, noise, and invalid returns;
- bumper/contact independent of the cognitive agent;
- battery state;
- controllable phone flashlight and robot lights;
- phone sensor rig mounted at the measured pose.

The ESP32/Arduino safety layer may stop the real or simulated rover when the
bumper is hit or a near-field range threshold is crossed. Gemma cannot override
that layer.

## Runtime evidence

The simulation launch publishes the physical sensor, normalized observation,
candidate, MetaView and action-result side of this contract plus isolated
`/pulso/sim/**` sources. The brain/audit topics appear only while a real Mac or
S25 Gemma runtime is connected; zero messages on them without a commander is
expected.

Headless HIL checks have observed RGB and normalized state, injected a
phone-side saliency clue, centered it, requested a fresh view, confirmed
flashlight on/off and exercised bounded navigation. Native brain-host and web
unit suites separately validate the exact-input join and rendering contracts.
For the current integrated route result and reproducible logs, use
`documentation/PULSO_VERIFICATION_AND_RECOVERY.md` rather than copying a test
count into this stable contract.

This proves the simulated boundary only. Physical parity still requires S25
bags and the `ANDROID_REAL` adapter; rates and noise values remain provisional
until that calibration is recorded.

## Acceptance checks

The sensor layer is acceptable only when:

1. all messages use simulation time and coherent timestamps;
2. the dense cloud aligns with RGB within a visible calibration target;
3. raw depth contains realistic holes and confidence values;
4. VIO drifts and can lose tracking while ground truth remains hidden;
5. wheel slip causes divergence between wheel odometry and VIO;
6. darkness degrades vision and the flashlight improves it;
7. removing an optional physical sensor removes its topic or marks it
   unavailable;
8. recorded simulation bags and Android bags can be replayed through the same
   Pulso perception interface;
9. every image claimed as Gemma input matches the audit JPEG SHA-256 and byte
   count;
10. simulator ground truth never appears in observations, candidates,
    MetaView or Gemma audit payloads.
