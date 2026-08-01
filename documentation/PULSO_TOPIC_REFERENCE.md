# PULSO — referencia de tópicos y contratos

Esta tabla sirve para saber quién produce cada dato, quién lo consume y si puede
entrar al cerebro. Los tipos corresponden al código ROS 2 actual.

## 1. Convenciones

- Frame cognitivo: `map`.
- Reloj: tiempo simulado de `/clock` para ROS; timestamps monotónicos dentro de
  los contratos JSON.
- JSON viaja en `std_msgs/msg/String` para conservar una frontera
  transport-neutral.
- Imágenes grandes viajan como `sensor_msgs`, no dentro del WorldState.
- Todo `/pulso/sim/**` es privado del simulador. Ningún brain debe suscribirse.

## 2. Flujo de sensores

| Tópico ROS | Tipo | Productor | Consumidor / uso |
| --- | --- | --- | --- |
| `/clock` | `rosgraph_msgs/msg/Clock` | Gazebo bridge | todos los nodos con `use_sim_time` |
| `/pulso/phone/rgb/image` | `sensor_msgs/msg/Image` | Gazebo bridge | RViz, compresión HIL |
| `/pulso/phone/rgb/compressed` | `sensor_msgs/msg/CompressedImage` | cloud adapter | brain, web, HIL |
| `/pulso/phone/rgb/camera_info` | `sensor_msgs/msg/CameraInfo` en `sim`; `std_msgs/msg/String` en `real` | Gazebo bridge o S25 | proyección/FOV; en `real`, `pulso.phone-camera-info.v1` para web |
| `/pulso/phone/telemetry` | `std_msgs/msg/String` | S25 `ANDROID_REAL` | `pulso.phone-telemetry.v1`: IMU, batería y temperatura para Mission Control |
| `/pulso/phone/depth/raw` | `sensor_msgs/msg/Image` | depth emulator | nube, artifacts |
| `/pulso/phone/depth/smoothed` | `sensor_msgs/msg/Image` | depth emulator | RViz |
| `/pulso/phone/depth/confidence` | `sensor_msgs/msg/Image` | depth emulator | QA de profundidad |
| `/pulso/phone/depth/points` | `sensor_msgs/msg/PointCloud2` | cloud adapter | scan, RViz, MetaView 3D |
| `/pulso/phone/arcore/feature_points` | `sensor_msgs/msg/PointCloud2` | cloud adapter | RViz / evidencia VIO |
| `/pulso/phone/imu/data_raw` | `sensor_msgs/msg/Imu` | Gazebo bridge | RViz / status |
| `/pulso/phone/vio/odom` | `nav_msgs/msg/Odometry` | VIO emulator | TF/SLAM/HIL/RViz |
| `/pulso/phone/vio/status` | `diagnostic_msgs/msg/DiagnosticArray` | VIO emulator | tracking epoch, HIL, safety cognitiva |
| `/pulso/base/wheel/odom` | `nav_msgs/msg/Odometry` | DiffDrive bridge | calibración / comparación de slip |
| `/pulso/base/sonar/front` | `sensor_msgs/msg/Range` | range adapter | safety, HIL, RViz |
| `/pulso/base/bumper` | `std_msgs/msg/Bool` | base adapter | safety, HIL |
| `/pulso/base/battery` | `sensor_msgs/msg/BatteryState` | base adapter | HIL, RViz |
| `/pulso/phone/flashlight/state` | `std_msgs/msg/Bool` | base adapter | confirmación de actuador |

## 3. Mapeo y navegación

| Tópico | Tipo | Significado |
| --- | --- | --- |
| `/pulso/navigation/scan` | `sensor_msgs/msg/LaserScan` | corte 2D 0.10–5 m de la nube depth |
| `/map` | `nav_msgs/msg/OccupancyGrid` | mapa SLAM incremental, 5 cm/celda |
| `/tf`, `/tf_static` | TF 2 | relación `map`, `odom`, rover y sensores |
| `/pulso/navigation/candidates` | `std_msgs/msg/String` | `pulso.navigation.candidates.v1` |
| `/pulso/navigation/metaview` | `sensor_msgs/msg/Image` | MetaView 2D raw para RViz |
| `/pulso/navigation/metaview/compressed` | `sensor_msgs/msg/CompressedImage` | MetaView 2D JPEG para brain/web |
| `/pulso/navigation/metaview_scene` | `std_msgs/msg/String` | geometría live `pulso.metaview-scene.v1` para visor 3D |

### `pulso.navigation.candidates.v1`

Cabecera:

```json
{
  "captured_monotonic_ns": 0,
  "sensor_map_seq": 0,
  "navigation_revision": 0,
  "valid_until_monotonic_ns": 0,
  "candidates": []
}
```

Cada candidato contiene `type`, `id`, `capability`, `target_revision`, label,
purpose, `position_m`, `path_length_m`, `risk`, `information_gain` y
`frontier_cells`. La capability nunca entra al prompt; el guard la agrega al
ActionIntent fuera de Gemma.

### `pulso.metaview-scene.v1`

Contiene:

- `frame_id=map`, timestamp, map seq y navigation revision;
- resolución, origen, dimensiones y conteos de la grilla;
- hasta 4,500 puntos libres y 4,500 ocupados muestreados de forma determinista;
- pose/heading del rover;
- hasta 1,600 puntos depth transformados por TF a `map`;
- huella del scan;
- hasta seis rutas con path, riesgo, información y estado selected;
- bounds de toda la evidencia.

No incluye celdas desconocidas ni malla/labels de Gazebo. La ocupación es 2.5D;
solo depth trae altura medida.

## 4. HIL cerebro ↔ cuerpo

| Tópico | Tipo | Dirección en rosbridge | Uso |
| --- | --- | --- | --- |
| `/pulso/hil/observation` | `std_msgs/msg/String` | cuerpo → brain/web | `pulso.observation.v1` |
| `/pulso/hil/action_intent` | `std_msgs/msg/String` | brain → navegación | `pulso.action.v1` |
| `/pulso/hil/action_result` | `std_msgs/msg/String` | navegación → brain/web | `pulso.action-result.v1` |
| `/pulso/hil/perception_tracks` | `std_msgs/msg/String` | detector Ubuntu/S25 → navegación/web | pistas YOLO de vida corta |
| `/pulso/hil/perception_telemetry` | `std_msgs/msg/String` | detector Ubuntu/S25 → web | provider, estado y latencia |
| `/pulso/hil/brain_trace` | `std_msgs/msg/String` | brain → web | traza pública acotada |
| `/pulso/hil/gemma_input` | `std_msgs/msg/String` | brain Ubuntu/S25 → web | entrada exacta y harness del turno |
| `/pulso/hil/gemma_view/compressed` | `sensor_msgs/msg/CompressedImage` | brain Ubuntu/S25 → web | JPEG exacto adjuntado al modelo |
| `/pulso/phone/telemetry` | `std_msgs/msg/String` | S25 → web | `pulso.phone-telemetry.v1` con accel/gyro y batería |
| `/pulso/phone/rgb/camera_info` | `std_msgs/msg/String` en `real` | S25 → web | `pulso.phone-camera-info.v1` con intrínsecos ARCore |

### Fronteras rosbridge

El bridge escucha en `127.0.0.1:9091`. Los perfiles son deny-by-default y
limitan mensajes a 4 MB.

En `sim`, el brain local puede publicar:

```text
/pulso/hil/action_intent
/pulso/hil/perception_tracks
/pulso/hil/brain_trace
/pulso/hil/gemma_input
/pulso/hil/gemma_view/compressed
/pulso/hil/perception_telemetry
```

Y suscribirse solo a:

```text
/pulso/hil/action_intent
/pulso/hil/observation
/pulso/navigation/candidates
/pulso/hil/action_result
/pulso/navigation/metaview/compressed
/pulso/navigation/metaview_scene
/pulso/phone/rgb/compressed
/pulso/phone/rgb/camera_info
/pulso/phone/telemetry
/pulso/hil/perception_tracks
/pulso/hil/brain_trace
/pulso/hil/gemma_input
/pulso/hil/gemma_view/compressed
/pulso/hil/perception_telemetry
```

Servicios y acciones ROS están denegados. El perfil `real` es más estrecho: el
S25 entra por `adb reverse` y solo publica observation/navigation, RGB,
MetaView, telemetría IMU/batería, intrínsecos, action results, percepción y
auditoría para Mission Control. No puede publicar `/pulso/hil/action_intent`,
`/cmd_vel_safe` ni suscribirse a `/pulso/sim/**`. Mantén 9091 en loopback.

### Telemetría física del teléfono

`pulso.phone-telemetry.v1` contiene `captured_monotonic_ns`, `source`,
`frame_id`, `imu.acceleration_mps2`, `imu.angular_velocity_radps`,
`battery.fraction` y `battery.temperature_c`. Un vector ausente queda `null`;
Mission Control no lo sustituye por una muestra sintética.

`pulso.phone-camera-info.v1` contiene timestamp, `frame_id`, fuente de
calibración, ancho/alto, modelo, distortion model y la matriz intrínseca `k` de
3×3. Este JSON es específico de `real`; en `sim`, el mismo nombre de tópico usa
el mensaje ROS nativo `sensor_msgs/msg/CameraInfo`. Los modos no deben ejecutarse
a la vez: use `./pulso stop` antes de cambiar entre ellos.

### Observación

`pulso.observation.v1` incluye:

- ID/fuente/timestamp/frame;
- tracking state, epoch, quality y cause;
- pose, heading/confianza, motion state, batería, flashlight, rango y bumper;
- referencias de artifacts RGB/depth/cloud con vigencia.

La observación agregada se publica a 2 Hz. Las imágenes continúan en sus
tópicos nativos con mayor frecuencia.

### ActionIntent

Campos principales de `pulso.action.v1`:

```text
action_id, mission_id, issued_monotonic_ns, kind, target, parameters,
candidate_capability, expected_navigation_revision,
expected_tracking_epoch, expected_target_revision
```

Acciones físicas: `STOP`, `MOVE_TO`, `LOOK_AT`, `REQUEST_VIEW` y
`SET_FLASHLIGHT`. `MOVE_TO`/`LOOK_AT` primero responden `ACTIVE` y después un
estado terminal.

Estados terminales relevantes:

```text
SUCCEEDED, BLOCKED, CANCELLED, REJECTED, TIMEOUT, ACTUATOR_TIMEOUT, BUSY,
DUPLICATE_ACTION, STALE_OR_UNKNOWN_TARGET, STALE_CAPABILITY,
EXPIRED_CAPABILITY, STALE_NAVIGATION_REVISION, STALE_TRACKING_EPOCH,
STALE_TARGET_REVISION, LOCALIZATION_UNAVAILABLE, UNSUPPORTED_ACTION
```

El brain host espera el terminal; `ACTIVE` no se interpreta como éxito.

## 5. Entrada exacta de Gemma

### `/pulso/hil/gemma_input`

Contrato de implementación: `pulso.gemma-input.v1`.

| Campo | Qué prueba |
| --- | --- |
| `input_id`, `turn_id`, `selected_world_seq` | identidad exacta del envío |
| `model_id`, `input_kind` | modelo y si es WorldPacket o tool result |
| `exact_message` | contenido ordenado entregado a la API pública del runtime, sin duplicar blob JPEG |
| `prompt_text` | texto del packet cuando corresponde |
| `image` | kind, fuente, timestamp, bytes, hash y tópico de auditoría |
| `system_prompt` + SHA-256 | instrucciones reales del harness |
| `tool_schemas` + SHA-256 | herramientas realmente declaradas |
| `context_tokens_before` | tokens antes del envío, si LiteRT los expone |
| `conversation_scope=TURN` | conversación nueva por ciclo |
| `conversation_reused_within_turn=true` | tool results siguen en el mismo turno |
| `conversation_reused_across_turns=false` | no arrastra chat al siguiente packet |

Cuando el mensaje contiene una imagen, el blob Base64 se reemplaza en el JSON
de auditoría por una referencia a `/pulso/hil/gemma_view/compressed`; los bytes
exactos viajan allí. Se enlazan con `jpeg_sha256`.

`gemma_input` puede contener el system prompt, schemas y resultados completos
de una skill. Es auditoría local de alta sensibilidad y no debe salir del host.

En Android, esta exactitud cubre el `Content`, `Instruction` y las
`FunctionDeclaration` entregadas a ADK. La serialización privada, tokenización o
transformación interna de ADK/LiteRT-LM no es observable por la API y no forma
parte del contrato.

### `/pulso/hil/brain_trace`

`pulso.brain-trace.v1` es deliberadamente más pequeño. Campos: `event_id`,
timestamp, turn/world, category, label, summary, latencia y attributes
allowlisted. No contiene capability, cuerpo de skill ni canales privados.

Categorías:

```text
CONTEXT → TOOL_REQUEST → TOOL_RESULT → MODEL_RESPONSE → CYCLE_COMPLETE
ERROR puede aparecer en cualquier punto.
```

## 6. Movimiento y safety

| Tópico | Tipo | Productor → consumidor |
| --- | --- | --- |
| `/pulso/base/cmd_vel_desired` | `geometry_msgs/msg/Twist` | controlador → safety |
| `/pulso/base/cmd_vel_safe` | `geometry_msgs/msg/Twist` | safety → DiffDrive |
| `/pulso/base/safety/status` | `diagnostic_msgs/msg/DiagnosticArray` | safety → nav/HIL/RViz |
| `/pulso/base/estop` | `std_msgs/msg/Bool` | operador/MCU → safety latch |
| `/pulso/phone/flashlight/cmd` | `std_msgs/msg/Bool` | navegación → body adapter |

El HIL externo no puede publicar directamente `/cmd_vel_safe`; el test de
seguridad comprueba ese aislamiento. Solo ActionIntent cruza el bridge.

## 7. Visualización ROS

| Tópico | Tipo | Display RViz |
| --- | --- | --- |
| `/pulso/navigation/candidate_markers` | `visualization_msgs/msg/MarkerArray` | rutas y endpoints A–F |
| `/pulso/navigation/selected_path` | `nav_msgs/msg/Path` | ruta elegida |
| `/pulso/navigation/executed_trajectory` | `nav_msgs/msg/Path` | trayectoria realizada |
| `/pulso/visualization/status_markers` | `visualization_msgs/msg/MarkerArray` | safety/misión/IMU |

Estos tópicos explican decisiones; no cambian navegación.

## 8. Verdad privada de simulación

Ejemplos:

```text
/pulso/sim/ground_truth/odom
/pulso/sim/phone/depth_clean
/pulso/sim/base/front_scan
/pulso/sim/base/bumper_contacts
```

Los adaptadores pueden usarlos para emular un sensor; el brain, panel y HIL no
deben poder suscribirse a ground truth. Si aparece uno en la allowlist de
rosbridge, es un fallo de aislamiento.

## 9. Inspección rápida

```bash
ros2 topic list | sort
ros2 topic info /pulso/navigation/metaview_scene
ros2 topic echo --once /pulso/hil/observation
ros2 topic echo --once /pulso/navigation/candidates
ros2 topic echo --once /pulso/hil/brain_trace
ros2 topic echo --once /pulso/hil/gemma_input
ros2 topic hz /pulso/phone/rgb/compressed
```

Evita imprimir repetidamente imágenes Base64 o `gemma_input` en una pantalla
pública: son grandes y pueden incluir instrucciones del harness.
