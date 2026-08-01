# Pulso

Pulso es un cerebro local y auditable para búsqueda y rescate. El mismo
contrato alimenta hoy dos fuentes implementadas:

- `GAZEBO_HIL`: mundo, sensores y cuerpo simulados en Gazebo/ROS 2;
- `ANDROID_REAL`: RGB y Depth de ARCore, pose VIO, IMU, torch Camera2, audio/TTS
  y Gemma 4 E4B local en el S25.

La autonomía no termina al alcanzar un frontier ni al verificar una persona.
Gemma mantiene la misión raíz como criterio terminal y continúa creando o
resolviendo subobjetivos hasta llamar `complete_mission`. El harness acepta ese
cierre solo si referencia la misión/goal vigentes y evidencia real conocida;
entonces emite STOP y bloquea nuevos ciclos.

La simulación tiene evidencia ejecutada con el S25 como único cerebro por
defecto. En HIL, E4B cargó con GPU en 11.385 s y el ciclo real del cerebro tardó
56.937 s de extremo a extremo, incluida la espera del resultado de acción:
canonicalizó de forma segura el ID propuesto, aceptó `MOVE_TO` y el SafetyGate
lo bloqueó por obstáculo. Esto valida cognición HIL; no equivale a locomoción.

El preflight físico verificó APK, modelo, cámara y bridge. ARCore `TRACKING` y
la nube real siguen pendientes porque el teléfono permaneció inmóvil y la
cámara no quedó expuesta al entorno. Zeus no se movió y su locomoción continúa
sin validar.

## Flujo único en Ubuntu 22.04

Los comandos funcionan desde cualquier checkout. Sin configuración adicional,
los datos pesados quedan bajo `${XDG_DATA_HOME:-$HOME/.local/share}/pulso`.
`PULSO_DATA_ROOT` solo es un override opcional para quien prefiera otro disco.

```bash
./pulso install
./pulso doctor
./pulso sim
```

`sim` inicia Gazebo Fortress, RViz, rosbridge y Mission Control. El único cerebro
esperado es la app del S25: ábrala y pulse `CONECTAR GAZEBO`. El fallback
`./pulso sim --host-brain` es solo de laboratorio; no conecte el agente S25 al
mismo tiempo. Mission Control queda en:

```text
SIM  http://127.0.0.1:4174/?profile=sim&bridge=ws://127.0.0.1:9092
REAL http://127.0.0.1:4173/?profile=real&bridge=ws://127.0.0.1:9091
```

Los perfiles usan `ROS_DOMAIN_ID` 43 y 42 respectivamente, y guardan sesiones
en directorios separados; pueden estar abiertos a la vez sin mezclar tópicos.

Con el S25 desbloqueado y autorizado por USB:

```bash
./pulso stop
./pulso real --dry-run
./pulso real
```

`real` verifica S25, APK y modelo, crea `adb reverse` para el bridge local,
concede permisos, abre la app y deja lista la telemetría observacional. En la
app, `CONECTAR S25` inicia el source físico. Mission Control recibe, entre otros,
`/pulso/phone/telemetry` y `/pulso/phone/rgb/camera_info`; verlos no equivale a
validación hasta completar la corrida supervisada y preservada por Atlas.

Para cerrar:

```bash
./pulso stop
```

## Frontera Zeus

El Zeus es Arduino UNO + shield de motores + ESP32-CAM, no Raspberry Pi. Su
cliente está en dry-run por defecto: valida comandos sin enviarlos a motores.
STOP se intenta al conectar, desarmar, expirar el TTL o fallar la conexión, pero
el protocolo stock no devuelve ACK; no se debe llamar “STOP confirmado”.

La locomoción física permanece bloqueada: faltan validación humana del rover,
dead-man del firmware, E-stop físico, costmap/trayectoria real y prueba con una
persona junto al paro.

## Artefactos fijados

| Artefacto | Revisión/tamaño | SHA-256 |
| --- | --- | --- |
| Gemma 4 E4B LiteRT-LM | `f7ad334…`, 3,659,530,240 B | `0b2a8980…52e0` |
| APK debug de entrega | 225609468 B | `949bae5458233e4b675b01c1b0d46ba2bc797442d0fa772a42cc0fddd59e19b0` |

Los binarios no se guardan en Git. Las revisiones completas están en
`infra/ubuntu/versions.env`.

## Mapa

| Ruta | Responsabilidad |
| --- | --- |
| `apps/pulso-android/` | Gemma E4B, HIL y source/actuadores físicos S25 |
| `apps/pulso-mission-control/` | cockpit observacional y auditoría |
| `contracts/` | observación, acción y trazas versionadas |
| `sim/ros2_ws/` | Gazebo, SLAM, navegación y safety ROS 2 |
| `infra/ubuntu/` | instalación y diagnóstico reproducibles |
| `documentation/` | runbook, arquitectura, seguridad y evidencia |

Empiece por [`PULSO_IMPLEMENTATION_RUNBOOK.md`](documentation/PULSO_IMPLEMENTATION_RUNBOOK.md).
La evidencia final y los comandos de la próxima ejecución están en
[`FINAL_VALIDATION.md`](documentation/evidence/FINAL_VALIDATION.md).
