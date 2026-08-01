# PULSO — runbook de entrega

Ruta canónica para Ubuntu 22.04. Distingue tres estados:

- **sim validado:** Gazebo usa el S25 como único cerebro por defecto y existe
  evidencia HIL real de E4B, tool y SafetyGate;
- **real implementado:** Camera/ARCore/IMU/torch/TTS/Gemma están conectados en
  código Android;
- **real parcialmente comprobado:** APK/modelo/cámara/bridge fueron verificados;
  ARCore `TRACKING`, nube y sesión sensorial completa siguen pendientes.

## 0. Seguridad

- Zeus permanece con ruedas levantadas o motores sin energía.
- El hardware es Arduino UNO + shield + ESP32-CAM.
- El cliente Zeus queda en dry-run; no habilite `liveMotorTransport`.
- STOP no tiene ACK en el protocolo stock. Considérelo intento no confirmado.
- La locomoción física requiere persona junto al paro, dead-man de firmware,
  E-stop físico y validación de costmap/trayectoria.

## 1. Preparar Ubuntu

```bash
cd /ruta/al/checkout/HACKATHON_ESAN
./pulso install
./pulso doctor
```

Por defecto, Pulso usa `${XDG_DATA_HOME:-$HOME/.local/share}/pulso`. Defina
`PULSO_DATA_ROOT=/ruta/en/otro/disco` solo si necesita mover modelos, SDK,
caches y entornos fuera de esa ubicación; no es requisito de instalación.

Resultado requerido: `doctor` termina con `failures=0`, reconoce ROS 2 Humble,
Gazebo Fortress, Android SDK 35, ADB, JDK 17/21, Blender, Node/Python y el E4B
fijado. Docker/NVIDIA pueden ser opcionales según el host.

## 2. Ejecutar la simulación completa

```bash
./pulso sim
```

La CLI inicia Gazebo, RViz, rosbridge local, Mission Control y la infraestructura
del mundo simulado. No inicia otro cerebro: la app del S25 es el único cerebro
por defecto.
Ábrala y pulse `CONECTAR GAZEBO`. Abra Mission Control en:

```text
http://127.0.0.1:4173/?bridge=ws://127.0.0.1:9091
```

Evidencia mínima:

| Vista | Evidencia |
| --- | --- |
| Gazebo | mundo, OpenBot, física y sensores simulados |
| RViz | `/map`, TF, depth/VIO y rutas vigentes |
| Mission Control | source HIL, RGB/MetaView y telemetría live |
| Gemma input | WorldPacket y JPEG exacto si hubo `request_view` |
| Timeline | tool tipada y resultado terminal del controlador |

`./pulso sim --headless` sirve para diagnóstico, no para la demo visual.

`./pulso sim --host-brain` habilita el runtime Ubuntu únicamente como fallback
de laboratorio. Nunca lo use a la vez que el agente del S25.

La evidencia final observó E4B GPU warm en 11.385 s. El ciclo HIL real tomó
56.937 s en total, incluida la espera de action result: el S25 canonicalizó el
ID propuesto, emitió un `MOVE_TO` aceptado y el SafetyGate lo bloqueó de forma
segura por obstáculo.

## 3. Preparar el S25

Condiciones: teléfono desbloqueado, depuración USB autorizada y exactamente un
dispositivo en `adb devices -l`.

`sim` y `real` son modos excluyentes. Si la simulación está abierta, ciérrela
antes de preparar el teléfono:

```bash
./pulso stop
./pulso real --dry-run
./pulso real
```

La primera orden revisa identidad/capacidades. La segunda:

1. valida APK y Gemma E4B por hash/tamaño;
2. inicia Mission Control y el bridge local deny-by-default;
3. crea `adb reverse` para `9091`;
4. instala el APK, copia/verifica E4B y concede cámara/audio;
5. abre la Activity.

No debe aceptar services/actions ni `/pulso/hil/action_intent` desde el teléfono.
La ruta real solo publica telemetría necesaria para Mission Control.

## 4. Ejecutar `ANDROID_REAL`

En la app:

1. pulse `CONECTAR S25`;
2. acepte instalación/actualización de Google Play Services for AR si aparece;
3. espere un estado `S25 TRACKING_DEPTH` o un estado degradado explícito;
4. confirme RGB, pose, IMU, batería, MetaView y depth/rango en la UI;
5. cargue Gemma y ejecute una decisión sin locomoción;
6. pruebe `request_view`, torch y una frase TTS corta;
7. preserve logs, hashes, latencias y temperatura.

Qué está implementado:

- RGB, intrínsecos y Depth16 de ARCore;
- pose VIO con epochs y acelerómetro/giroscopio;
- ocupación/MetaView local derivados de depth;
- torch Camera2 con callback de confirmación;
- TTS terminal y escucha PCM acotada sin persistir audio crudo;
- Gemma 4 E4B local, tools tipadas y auditoría exacta.

Qué no puede afirmarse todavía: que esa cadena funciona de extremo a extremo
con sensores físicos. El preflight comprobó APK/modelo/cámara/bridge, pero el
teléfono estuvo inmóvil y sin la cámara expuesta; no se obtuvo ARCore
`TRACKING` ni nube real. Atlas debe confirmar esos puntos antes de promover la
ruta sensorial a “validada”.

## 5. Zeus durante la prueba

Se permiten solo:

- conexión/desconexión en dry-run;
- validación de comandos sin envío a motores;
- intentos STOP explícitamente marcados `UNCONFIRMED`.

No se permite locomoción física. `MOVE_TO` real está bloqueado hasta probar un
costmap físico y el validator de trayectoria; el armado live exige además
dead-man verificado y presencia humana explícita.

## 6. Leer Mission Control

- **Cabecera:** bridge, source, VIO, modelo y misión.
- **RGB/sensores:** bytes del source activo y medidas físicas/simuladas.
- **S25 físico:** `/pulso/phone/telemetry` muestra IMU/batería y
  `/pulso/phone/rgb/camera_info` muestra intrínsecos recibidos, sin mocks.
- **Mapa/MetaView:** evidencia derivada, pose y candidatos.
- **Gemma input:** mensaje, tools y JPEG en la frontera pública de ADK.
- **Timeline:** causalidad auditable, nunca chain-of-thought.
- **SOLO GEMMA:** filtra input exacto, vista exacta, contexto, tools,
  resultados, respuesta pública y cancelación del turno.
- `WAITING` significa que falta evidencia; no existe modo sintético de respaldo.

## 7. Cierre

```bash
./pulso stop
```

Detiene app, bridge, web, brain y simulación gestionados; retira `adb reverse`.
Logs y PIDs quedan bajo:

```text
${PULSO_STATE_ROOT:-$HOME/.local/state/pulso}/orchestrator/
```

Si un proceso no responde, la CLI lo informa sin usar `SIGKILL` automático.

## 8. Frase correcta de entrega

> PULSO tiene un vertical E4B validado en simulación y una ruta `ANDROID_REAL`
> implementada para RGB, Depth, VIO, IMU, torch, TTS y Gemma local. El S25 ya
> pasó una decisión HIL real con veto seguro del SafetyGate. El preflight físico
> verificó APK/modelo/cámara/bridge, pero `TRACKING` y nube siguen pendientes.
> Zeus no se movió y la locomoción física continúa sin validar.

Para la secuencia exacta de instalación, operación y túnel SSH de la próxima
ejecución, use [`evidence/FINAL_VALIDATION.md`](evidence/FINAL_VALIDATION.md).
