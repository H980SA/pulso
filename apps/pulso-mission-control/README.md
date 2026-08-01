# PULSO Mission Control

Cockpit web para simulación y S25 físico. Consume únicamente evidencia live; si
un tópico falta muestra `WAITING` y no inyecta replay ni resultados ficticios.
En el perfil real publica solo el contrato operador acotado y `PARAR TODO`.

## Ejecutar

Use la CLI desde la raíz:

```bash
./pulso sim
# o, con el S25 autorizado:
./pulso real
```

Abra el perfil correspondiente:

```text
REAL http://127.0.0.1:4173/?profile=real&bridge=ws://127.0.0.1:9091
SIM  http://127.0.0.1:4174/?profile=sim&bridge=ws://127.0.0.1:9092
```

REAL usa `ROS_DOMAIN_ID=42`; SIM usa `ROS_DOMAIN_ID=43`. Cada servidor conserva
su propio SQLite y sus artefactos, de modo que las grabaciones no se mezclan.

En `real`, el teléfono llega al bridge local mediante `adb reverse`. Mission
Control no necesita acceso de red externo.

## Qué muestra

- MetaView 3D/2D con ocupación, depth medido, pose y candidatos.
- RGB del source activo y pistas del detector.
- observation, VIO, batería, rango y torch.
- `action_result` terminal o fallo explícito.
- input público exacto de Gemma, JPEG adjunto y SHA-256.
- traza causal `CONTEXT → TOOL_REQUEST → TOOL_RESULT → CYCLE_COMPLETE`.

En `BRAIN TIMELINE`, `SOLO GEMMA` filtra únicamente entradas exactas, imagen
multimodal exacta, contexto, solicitud/resultado de tools, respuesta pública,
cancelación y cierre de ciclo. Al seleccionar un evento se muestran system
prompt, WorldPacket/mensaje, schemas, propiedades públicas y timestamps reales;
si el dato no fue recibido aparece vacío, nunca se sustituye con una muestra.

Los controles `SEGUIR`, `CENITAL`, `ENCUADRAR` y selección de ruta solo cambian
la cámara del operador.

## Tópicos de entrada

| Tópico | Tipo | Uso |
| --- | --- | --- |
| `/pulso/hil/observation` | `std_msgs/msg/String` | source, pose, VIO, batería, rango y torch |
| `/pulso/navigation/candidates` | `std_msgs/msg/String` | candidatos medidos y revisionados |
| `/pulso/navigation/metaview_scene` | `std_msgs/msg/String` | ocupación, depth, rover y rutas 3D |
| `/pulso/navigation/metaview/compressed` | `sensor_msgs/msg/CompressedImage` | MetaView 2D |
| `/pulso/phone/rgb/compressed` | `sensor_msgs/msg/CompressedImage` | cámara sim o S25 |
| `/pulso/hil/action_result` | `std_msgs/msg/String` | resultado verificable |
| `/pulso/hil/perception_tracks` | `std_msgs/msg/String` | pistas visuales |
| `/pulso/hil/perception_telemetry` | `std_msgs/msg/String` | provider y latencia |
| `/pulso/hil/brain_trace` | `std_msgs/msg/String` | traza pública |
| `/pulso/hil/gemma_input` | `std_msgs/msg/String` | entrada/harness público exacto |
| `/pulso/hil/gemma_view/compressed` | `sensor_msgs/msg/CompressedImage` | JPEG exacto del turno |

La ruta real debe ser deny-by-default: solo estos publishers de telemetría,
sin services/actions y sin aceptar `/pulso/hil/action_intent` desde el teléfono.
Mission Control nunca necesita capacidad de mando.

## Privacidad

`gemma_input` puede contener system prompt, tool schemas y resultados. Se queda
en loopback y no se publica externamente. La traza pública usa allowlist y
excluye chain-of-thought, capabilities y cuerpos de skills.

## Verificar

```bash
npm test
python3 -m py_compile server.py
```
