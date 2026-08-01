# PULSO Brain Host — Gemma real por LiteRT-LM

Este runtime Ubuntu es un fallback de laboratorio. La ruta de producto
`./pulso sim` usa el S25 como único cerebro por defecto; para activar este host
se requiere `./pulso sim --host-brain`, sin conectar el agente S25 a la vez.

Este proceso está configurado para ejecutar **Gemma 4 E4B** en macOS o Ubuntu
con el paquete oficial `litert-lm-api==0.13.1`. Mantiene el `Engine` caliente y una `Conversation`
caliente durante cada ciclo (WorldPacket + tool results), lee el mundo simulado
por rosbridge y emite únicamente acciones comprobables.
No contiene un planner sintético ni respuestas pregrabadas.

## Qué entra realmente al modelo

Cada ciclo selecciona como máximo cinco candidatos frescos y construye el mismo
tipo de `CognitiveBrief` selectivo usado por Android: misión/goal persistentes,
pose y VIO actuales, último resultado físico, checkpoint compacto, pregunta
vigente y candidatos tipados. Nunca entrega capabilities opacas en el prompt.

Las imágenes no se adjuntan continuamente. Gemma primero llama
`request_view`; el host publica la acción real, espera `SUCCEEDED`, espera un
JPEG **posterior** al pedido y recién lo adjunta al siguiente WorldPacket. La
misma secuencia JPEG, sin recodificar, se reenvía a
`/pulso/hil/gemma_view/compressed`. Su SHA-256 aparece en el prompt y en
`/pulso/hil/gemma_input`, por lo que el panel puede probar qué vio Gemma.

`/pulso/hil/gemma_input` contiene el texto exacto, el system prompt, los schemas
de tools, el orden de contenido y el resultado exacto de cada tool. El blob de
imagen no se duplica dentro del JSON: su referencia y hash están allí, y sus
bytes exactos están en el tópico de imagen. La traza pública nunca publica los
campos privados/channels del modelo ni chain-of-thought. La conversación se
cierra al completar el turno y la siguiente decisión empieza limpia; esto evita
context rot. El checkpoint solo conserva hallazgos, resultados y el ID de una
skill, nunca su cuerpo de instrucciones.

## Tools reales

- `move_to`, `look_at`: requieren ID, tipo, revision, epoch y capability del
  packet elegido; esperan resultado terminal (`SUCCEEDED`, `BLOCKED`, etc.).
- `request_view`: además espera un frame nuevo de MetaView o RGB y agenda esa
  imagen para un solo turno.
- `stop`: publica `STOP` y espera confirmación.
- `set_flashlight`: publica el actuador y exige confirmación; si el cuerpo no
  lo soporta devuelve el error real.
- `load_skill`: solo carga información procedural local. No mueve el robot ni
  publica una acción fingida.

Ante timeout de movimiento se envía un `STOP` best-effort. Si cambia la revision
de navegación, el tracking epoch o la capability después de seleccionar el
packet, la tool rechaza el objetivo como stale antes de publicar movimiento.
Una respuesta stale se reinyecta una sola vez a Gemma para conservar el
protocolo de tools; ese turno termina inmediatamente después y queda agendado
un único WorldPacket fresco. Aunque el modelo repita varias llamadas stale en
la misma respuesta, no se consumen las restantes ni se agota el presupuesto de
tools con el mismo objetivo vencido.
Si rosbridge se reinicia, se invalidan geometría e imágenes y el proceso intenta
reconectar conservando el Engine y la memoria compacta; nunca reutiliza una
capability anterior a la desconexión.
También puede arrancar antes que la simulación: reintenta la conexión con backoff
acotado y no crea un WorldPacket hasta recibir contratos nuevos.

## Planificación semántica y térmica

El host es dirigido por eventos; no despierta Gemma en cada publicación ni por
un polling fijo. Una actualización de navegación agenda un turno solamente si
cambia la semántica de candidatos que Gemma puede usar: tipo, ID, etiqueta,
propósito, longitud, riesgo o ganancia de información, a la misma precisión de
dos decimales del prompt. El orden, timestamps, secuencias, revisions,
capabilities, vencimientos y revisions internas de targets actualizan el estado
vivo para validar tools, pero por sí solos no disparan inferencia.

Los eventos semánticos se coalescen y se admite como máximo un nuevo turno cada
`PULSO_SEMANTIC_COOLDOWN_S` segundos, medidos desde que terminó el turno
anterior. El valor predeterminado para E4B es `8.0` y el rango aceptado es
`0..60`. El primer turno no espera. Tampoco esperan la captura fresca que pidió
un `request_view`, una pérdida/cambio de epoch de tracking, el cierre del
proceso ni una desconexión de rosbridge; así la evidencia solicitada entra al
siguiente turno sin demora artificial.

Este límite solo controla inferencias semánticas costosas. Las comprobaciones
deterministas de capability/revision/epoch, los timeouts de tools y el `STOP`
best-effort se ejecutan dentro del turno actual y nunca quedan detrás del
cooldown. `PULSO_MIN_CYCLE_INTERVAL_S` se conserva únicamente por compatibilidad
con herramientas de perfilado antiguas y ya no gobierna el loop del host.

## Requisitos

Desde la raíz del proyecto deben existir:

```text
.tools/venvs/litert-lm-py313/bin/python
.tools/models/gemma-4-E4B-it.litertlm
```

El artefacto objetivo es
[`litert-community/gemma-4-E4B-it-litert-lm`](https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm):
`gemma-4-E4B-it.litertlm`, 3,659,530,240 bytes, SHA-256
`0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0`.
El `model_id` publicado en telemetría es el nombre del archivo configurado por
`PULSO_GEMMA_MODEL`, no una constante de familia; así los overrides siguen
siendo auditables sin revelar la ruta del host.

En Ubuntu 22.04 el runtime reproducible usa Python 3.10 en
`/mnt/linux-data/pulso/venvs/litert-lm-py310`; el Mac de desarrollo usa el
runtime Python 3.13 incluido en el proyecto. Python 3.9 no es compatible con
`dataclass(kw_only=True)` usado por LiteRT-LM 0.13.1.

La wheel Linux GPU 0.13.1 cierra el engine correctamente pero puede segfaultar
después, durante los finalizadores globales de CPython/OpenCL. PULSO evita esa
segunda finalización únicamente tras un cierre normal y esperado; el engine y
la conversación ya fueron cerrados. `PULSO_LITERT_LINUX_CLEAN_EXIT=python`
desactiva el workaround para diagnóstico. Un fallo inesperado sigue llegando
sin alterar al supervisor, que registra código y señal.

Rosbridge debe permitir publicar estos tópicos adicionales:

```text
/pulso/hil/gemma_input             std_msgs/msg/String
/pulso/hil/gemma_view/compressed   sensor_msgs/msg/CompressedImage
```

## Ejecutar

Con la simulación y rosbridge activos:

```bash
cd apps/pulso-brain-host
./run.sh
```

En segundo plano:

```bash
./start.sh
./status.sh
tail -f "${XDG_STATE_HOME:-$HOME/.local/state}/pulso/brain-host/brain-host.log"
./stop.sh
```

El estado operativo vive fuera del árbol desplegable por defecto, en
`${XDG_STATE_HOME:-$HOME/.local/state}/pulso/brain-host`. Así un reemplazo de
`apps/pulso-brain-host` no borra el PID, el log ni el último código de salida.
`start.sh` exige que el proceso sobreviva diez segundos, pero no presenta eso
como prueba de rosbridge o de inferencia. `status.sh` distingue explícitamente
estado de proceso y salud desconocida. Si Python/LiteRT termina por señal, el
supervisor deja `brain-host.exit` con `exit_code` y `signal`; `run.sh` habilita
`faulthandler` y salida sin buffer para conservar el último checkpoint posible.
`PULSO_BRAIN_RUNTIME_DIR` y `PULSO_STARTUP_GRACE_S` permiten ajustar las rutas y
la ventana sin cambiar código.

## Despliegue Ubuntu sin borrar evidencia

Desde la raíz del proyecto, `scripts/deploy_brain_host.sh` copia primero a una
release inmutable, repite la comparación con checksum y solo después cambia el
symlink `apps/pulso-brain-host` con un rename atómico. No arranca el host ni la
simulación y no borra releases anteriores:

```bash
./scripts/deploy_brain_host.sh
```

El script se niega a sustituir un `apps/pulso-brain-host` que sea un directorio
real; esa primera migración debe resolverse explícitamente para no perder datos.
Sus defaults son `diego@192.168.18.51`, la llave
`.tools/ssh/pulso_ubuntu_ed25519` y `/mnt/linux-data/pulso/repo`; se pueden
cambiar con `PULSO_UBUNTU_REMOTE`, `PULSO_UBUNTU_SSH_KEY` y
`PULSO_REMOTE_PROJECT_ROOT`. El runtime y sus logs siguen fuera de cada release.

Variables útiles:

```bash
PULSO_ROSBRIDGE_URL=ws://192.168.18.51:9091
PULSO_GEMMA_MODEL=/ruta/gemma-4-E4B-it.litertlm
PULSO_LITERT_BACKEND=gpu
PULSO_MAX_CONTEXT_TOKENS=4096
PULSO_SEMANTIC_COOLDOWN_S=8.0
```

## Flujo observable

1. `CONTEXT / WorldPacket selected` identifica el `world_seq` exacto.
2. `gemma_input` publica la entrada antes de ejecutar inferencia.
3. Si hay imagen, `gemma_view/compressed` publica el mismo JPEG adjuntado.
4. `TOOL_REQUEST` muestra argumentos públicos.
5. La acción viaja por `/pulso/hil/action_intent` y el host espera
   `/pulso/hil/action_result`.
6. `TOOL_RESULT` muestra el resultado físico; se reinyecta al modelo.
7. `MODEL_RESPONSE` publica solo texto ordinario y `CYCLE_COMPLETE` la latencia.

## Pruebas

```bash
../../.tools/venvs/litert-lm-py313/bin/python -m unittest discover -s tests -v
```

Las unitarias usan un engine y websocket falsos únicamente para probar el
arnés; el ejecutable productivo no tiene modo mock ni fallback sintético.

El ledger `evidence/native-model-smoke-2026-07-31.json` conserva un smoke
histórico de Gemma 4 E2B y no se presenta como validación de E4B. La evidencia
nativa E4B está en `sim/logs/e2e/gemma4-e4b-native-profile.json` (warm 11,666
ms; inferencia 1,518 ms; tool call esperado). La corrida estricta no-mock
`sim/logs/e2e/e4b-final-20260801T071618Z/e2e-report.json` terminó `ok=true`
con identidad `gemma-4-E4B-it.litertlm`, hashes de runtime válidos, imágenes
byte-exactas y dos `MOVE_TO ACTIVE→SUCCEEDED`.
