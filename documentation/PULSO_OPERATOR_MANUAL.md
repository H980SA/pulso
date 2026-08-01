# PULSO — manual del operador

Manual para ejecutar la simulación o el source físico S25 sin habilitar
locomoción Zeus. El runbook corto y autoritativo es
[`PULSO_IMPLEMENTATION_RUNBOOK.md`](PULSO_IMPLEMENTATION_RUNBOOK.md).

## 1. Estados de madurez

| Ruta | Estado |
| --- | --- |
| Gazebo + cerebro S25 | implementada; S25 es el único cerebro por defecto |
| Host E4B Ubuntu | fallback `--host-brain` de laboratorio, nunca simultáneo |
| APK/Gemma en S25 | artefactos fijados; cada sesión vuelve a verificar |
| Cognición S25 en HIL | validada: canonicalización, `MOVE_TO` aceptado y veto SafetyGate |
| `ANDROID_REAL` sensorial | APK/modelo/cámara/bridge verificados; `TRACKING`/nube pendientes |
| Zeus dry-run/STOP | implementado; STOP no tiene ACK |
| Locomoción Zeus | bloqueada y no validada |

No confunda pruebas unitarias/build con evidencia del teléfono. Solo Atlas puede
promover la ruta real después de observar y preservar una corrida.

## 2. Instalación

```bash
cd /ruta/al/checkout/HACKATHON_ESAN
./pulso install
./pulso doctor
```

El bootstrap es idempotente y no edita el shell profile. Usa
`${XDG_DATA_HOME:-$HOME/.local/share}/pulso` por defecto. `PULSO_DATA_ROOT` es
solo un override opcional para conservar modelos, caches y venvs en otro disco.

## 3. Operar simulación

```bash
./pulso sim
```

Abra Pulso en el S25 y pulse `CONECTAR GAZEBO`. No arranque el host Ubuntu: por
defecto el teléfono es el único cerebro. `./pulso sim --host-brain` queda
reservado para laboratorio y exige que el agente S25 esté desconectado.

Abra `http://127.0.0.1:4173/?bridge=ws://127.0.0.1:9091`.

### Gazebo

- La escena muestra física, colisiones, sobrevivientes y el OpenBot simulado.
- Ver movimiento prueba ejecución simulada, no que Gemma lo haya ordenado.
- La atribución requiere `gemma_input`, tool request y action result.

### RViz

- `Discovered SLAM Map`: ocupación acumulada.
- `TF / Sensor Frames`: `map → odom → base → phone`.
- Phone sensors: RGB, depth, VIO, IMU, scan y sonar.
- Pulso decisions: candidatos, ruta elegida, trayectoria y safety.
- Un display vacío exige comprobar su tópico; no habilita datos ficticios.

### Mission Control

- `ENLACE`: WebSocket local.
- `FUENTE`: `GAZEBO_HIL` o `ANDROID_REAL` reportado.
- `LO QUE GEMMA RECIBE`: input/harness público exacto.
- `IMAGEN ANEXADA`: bytes unidos por SHA-256 al turno.
- Sensores físicos: IMU/batería de `/pulso/phone/telemetry` e intrínsecos de
  `/pulso/phone/rgb/camera_info`, siempre como datos recibidos.
- Timeline: observación, input, tool, acción y resultado terminal.

Los controles de MetaView solo cambian la cámara del operador. La página es
observacional y muestra `WAITING` ante una fuente ausente.

## 4. Preparar el S25

1. Desbloquee el teléfono.
2. Active depuración USB y acepte la huella del host.
3. Confirme exactamente un dispositivo `device`.
4. Mantenga Zeus sin energía de motores o con ruedas levantadas.

```bash
adb devices -l
./pulso stop
./pulso real --dry-run
./pulso real
```

La CLI verifica artefactos, instala/copia el modelo, concede cámara/audio, crea
el túnel ADB y abre Pulso. Mission Control sigue en loopback del host.
`./pulso stop` es obligatorio al cambiar desde `sim`: los dos modos no comparten
una sesión activa.

## 5. Iniciar source físico

Pulse `CONECTAR S25`. La Activity mantiene el `GLSurfaceView` que ARCore necesita.

Estados esperables:

| Estado | Significado |
| --- | --- |
| `ARCORE_INSTALL_REQUESTED` | instalar/actualizar AR y reintentar |
| `TRACKING_PAUSED:*` | aún no hay pose válida |
| `TRACKING_NO_CURRENT_DEPTH` | VIO vivo; frame depth no disponible todavía |
| `TRACKING_TORCH_UNCONFIRMED` | source vivo; Camera2 no confirmó torch |
| `TRACKING_DEPTH` | pose y depth actuales disponibles |
| `THERMAL_STOP:*` | acciones físicas pausadas por temperatura |

La ausencia temporal de RGB/depth no se rellena. El operador debe mover el S25
despacio, con luz/textura suficientes y sin tapar cámara o IMU.

## 6. Evidencia S25 que falta capturar

Para declarar runtime validado se necesita una única sesión enlazada con:

- identidad/hash de APK y E4B en host y teléfono;
- arranque ARCore y secuencia de estados;
- RGB, Depth16, pose VIO e IMU observados;
- MetaView/candidatos derivados de medidas reales;
- carga E4B, warm latency y turnos con input/tool/result;
- torch confirmado, TTS completado y audio acotado;
- temperatura, batería, reconexión y cierre limpio;
- cero motion frames enviados a Zeus.

El corte físico ya comprobó APK, modelo, cámara y bridge. Como el teléfono quedó
inmóvil y la cámara no estuvo expuesta al entorno, no hubo ARCore `TRACKING` ni
nube física. Hasta capturar esos puntos, describa `ANDROID_REAL` como
implementado y parcialmente comprobado, no como sensor runtime validado.

## 7. Gemma y tools en campo

Gemma 4 E4B permanece local. Cada nuevo WorldPacket abre una conversación
limpia; tool results continúan solo dentro del turno actual.

- `request_view` espera un frame físico fresco.
- `set_flashlight` exige callback Camera2.
- `speak` espera callback terminal TTS.
- `listen` conserva métricas/hash, no PCM crudo.
- `stop_motion` intenta STOP Zeus sin afirmar ACK.
- `move_to` físico permanece bloqueado.
- `complete_mission` es la única condición terminal del loop. Gemma la llama
  solo cuando considera completa la misión raíz, no por acabar una ruta,
  inspeccionar/verificar una persona o completar un subobjetivo.

El guard comprueba `mission_id`, `goal_id` y `evidence_refs` contra el estado
vigente. Si acepta el cierre, pausa autonomía, invalida nuevas tools y manda
STOP. Si faltan candidatos, Gemma espera una revisión fresca del mapa sin
inventar IDs; el loop continúa cuando cambie la evidencia.

`DETENER` preempta el turno aunque E4B esté generando: la app libera `busy`,
invalida el lease de tools y envía STOP. E4B queda caliente para reanudar con
menor latencia. En Mission Control use `BRAIN TIMELINE → SOLO GEMMA` para ver el
input exacto, la explicación pública, cada tool y el resultado devuelto.

## 8. Zeus

El transport default es dry-run. Conectar intenta STOP y deja el arm state en
false. Un comando de movimiento requiere armado explícito; en dry-run se valida
pero no se transmite. Para modo live el código exige dead-man verificado y
persona presente, pero esas precondiciones aún no están satisfechas por la
entrega.

El TTL de 300 ms intenta STOP y desarma. Una caída de Android/Wi-Fi aún puede
derrotar un watchdog solo cliente; por eso se exige watchdog/dead-man MCU antes
de energizar motores.

## 9. Fallos rápidos

| Síntoma | Acción |
| --- | --- |
| `doctor` falla | corregir el FAIL antes de iniciar |
| puerto 9091 ocupado | `./pulso stop`; revisar PID/log, no matar procesos ajenos |
| pantalla Gazebo negra | revisar sesión gráfica y `QT_XCB_GL_INTEGRATION` |
| S25 no aparece | cable, desbloqueo y autorización ADB |
| ARCore solicita install | completar instalación, volver a Activity y pulsar `CONECTAR S25` |
| no hay depth | esperar frame, iluminar/mover; no inferir cero obstáculos |
| thermal stop | detener misión y enfriar; no desactivar el guard |
| Mission Control `WAITING` | revisar bridge/tópico; no sustituir por replay |

## 10. Cierre

```bash
./pulso stop
```

La CLI fuerza el cierre de la app si existe un solo device, retira `adb reverse`
y detiene procesos gestionados. STOP Zeus sigue siendo no confirmado: el cierre
de software no sustituye cortar energía ni el E-stop físico.

Logs: `${PULSO_STATE_ROOT:-$HOME/.local/state/pulso}/orchestrator/logs/`.

La secuencia de la próxima ejecución, incluido acceso remoto seguro, está en
[`evidence/FINAL_VALIDATION.md`](evidence/FINAL_VALIDATION.md).
