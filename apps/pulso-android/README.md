# Pulso Android

El runtime local mantiene Gemma 4 E4B cargado en el S25 durante la misión.
La corrida runtime completa de ARCore TRACKING, nube de puntos y locomoción Zeus se valida presencialmente; el preflight nocturno no la sustituye.

La app es el brain host de producción. Mantiene Gemma 4 E4B local y caliente
durante una misión y cambia la fuente detrás de `PulsoSensorSource`:

- `GAZEBO_HIL`: contratos normalizados recibidos del simulador;
- `ANDROID_REAL`: Camera/ARCore/IMU físicos del S25;
- `REPLAY`: fixtures deterministas para pruebas, no una ruta de producción.

La cognición S25 sí quedó observada en `GAZEBO_HIL`: E4B GPU warm en 11.385 s,
ciclo total de 56.937 s incluida la espera de action result, canonicalización
segura del target y veto por obstáculo del SafetyGate. `ANDROID_REAL` está
implementado y su preflight verificó APK/modelo/cámara/bridge, pero aún no hay
ARCore `TRACKING` ni nube física porque el teléfono estuvo inmóvil y la cámara
no estuvo expuesta. Tampoco se afirman térmica sostenida ni locomoción Zeus.

## Source físico implementado

`AndroidRealSource` usa ARCore 1.54 sobre un `GLSurfaceView` vivo:

1. solicita/abre ARCore y habilita Depth automático cuando el S25 lo soporta;
2. captura RGB de cámara, intrínsecos y `DEPTH16` sin inventar puntos;
3. transforma pose VIO a `arcore_world` y conserva `tracking_epoch`;
4. obtiene acelerómetro, giroscopio, batería y temperatura;
5. integra una ocupación local derivada y genera MetaView/candidatos;
6. publica `SensorFrame` con frescura y evidencia medible.

Si RGB o depth aún no están disponibles, quedan ausentes; no hay fallback
sintético. El guard térmico pausa acciones físicas a 42 °C y exige enfriamiento
antes de reanudar.

## Actuadores físicos

- `PhoneTorchActuator`: Camera2 y callback de confirmación de estado.
- `PhoneAudioActuator`: TTS con callback terminal y captura PCM acotada para
  `listen`; el audio crudo no se persiste.
- `request_view`: adjunta solo bytes de un frame físico fresco autorizado.
- `GemmaRuntime`: E4B local con conversación limpia por turno y tools tipadas.

## Zeus: integración sin locomoción habilitada

`ZeusWebSocketClient` usa dry-run por defecto. En ese modo valida frames pero no
los envía a motores. Cualquier motion frame exigiría conexión, armado explícito,
persona presente y dead-man de firmware verificado. `MOVE_TO` físico además se
rechaza hasta probar costmap y validación de trayectorias reales.

STOP se intenta al conectar, desarmar, expirar el TTL de 300 ms, desconectar o
fallar. El protocolo stock Zeus no tiene ACK: el resultado correcto es
`STOP_*_UNCONFIRMED`, nunca “detenido confirmado”.

## Flujo cognitivo

1. El source normaliza un `SensorFrame` real o simulado.
2. Los proyectores deterministas construyen `WorldState` y candidatos vigentes.
3. `ContextSelector` entrega a Gemma solo un `WorldPacket` relevante.
4. Una imagen entra únicamente después de `request_view`.
5. ADK Kotlin ejecuta Gemma 4 E4B sin historial entre turnos.
6. Las tools aceptan IDs/revisiones/capabilities del packet actual.
7. `complete_mission` es la única salida terminal semántica: un frontier,
   inspección, persona o subgoal completado no detiene por sí solo el agente.
8. La telemetría pública muestra input, respuesta, tool y resultado, no
   chain-of-thought.

`DETENER`, pérdida de heartbeat y thermal stop cancelan el Job activo, invalidan
el lease de tools del turno y mandan STOP sin descargar E4B. Una respuesta o
tool que llegue tarde recibe `CANCELED_TURN` y no cambia estado.

## Construir y ejecutar

Desde la raíz en Ubuntu:

```bash
./pulso install
./pulso doctor
scripts/android/build_debug.sh ws://127.0.0.1:9091
./pulso real --dry-run
./pulso real
```

El modelo queda fuera del APK en:

```text
/sdcard/Android/data/com.pulso.app/files/models/gemma-4-E4B-it.litertlm
```

`pulso real` valida artefactos, usa `adb reverse`, concede cámara/audio e inicia
la Activity. Después el operador pulsa `CONECTAR S25` para iniciar ARCore. Hasta
capturar `TRACKING` y nube con movimiento/cámara expuesta, “implementado” no
significa “sensor físico validado”.

Para apagar app, bridge y procesos:

```bash
./pulso stop
```

## Evidencia de auditoría

La app publica, solo hacia Mission Control local:

- observation, navigation, RGB y MetaView físicos;
- `action_result`, percepción y traza pública;
- `gemma_input` y el JPEG exacto autorizado por SHA-256.

La frontera exacta es `Content`, `Instruction` y `FunctionDeclaration` que la
app entrega a ADK. No se afirma acceso a tokenización, serialización privada o
razonamiento interno de LiteRT-LM.
