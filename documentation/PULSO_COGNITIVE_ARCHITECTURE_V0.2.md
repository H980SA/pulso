# Pulso: arquitectura cognitiva V0.2

Estado: especificación vigente aprobada, con refinamientos posteriores a V0.1.  
Fecha original: 2026-07-31. Decisión de modelo actualizada: 2026-08-01.  
Ámbito: núcleo cognitivo, contexto multimodal, memoria, skills, active perception y
contrato de herramientas.

Gemma 4 E4B es el target cognitivo vigente. Su perfil nativo, APK y E2E estricto
de simulación ya están preservados. `ANDROID_REAL` implementa Camera/ARCore,
IMU, torch, audio/TTS y E4B local en código, pero inferencia, latencia, térmica
y calidad sensorial runtime siguen pendientes como gate separado. La evidencia
E2B pertenece al baseline
histórico del arnés y se conserva en el ledger.

Documentos relacionados:

- [Contrato de sensores simulados](../docs/simulation/SENSOR_CONTRACT.md)
- [Alcance del rover de simulación](../docs/simulation/ROBOT_SCOPE.md)
- [Arquitectura cognitiva V0.1](PULSO_COGNITIVE_ARCHITECTURE_V0.1.md)

## 1. Cambios principales frente a V0.1

1. Un viewpoint ya no se invalida por cualquier nuevo punto del mapa.
2. Se distinguen actualizaciones de sensores de revisiones materiales de
   navegación, target y tracking.
3. Gemma nunca recibe el WorldState completo.
4. MetaView se adjunta solo cuando Gemma solicita una operación espacial.
5. MetaView usa colores neón, IDs, números y patrones redundantes.
6. CognitiveBrief es una composición híbrida: hechos deterministas más estado
   cognitivo estructurado persistido por Gemma.
7. Misión, objetivo e hipótesis quedan relacionados mediante IDs.
8. El catálogo de skills ya no muestra estimaciones de tokens.
9. Se precisa la diferencia entre viewpoints y frontiers.
10. `move_to` acepta objetivos tipados, no coordenadas inventadas por Gemma.

## 2. Decisión física inicial

El Samsung S25 estará fijo horizontalmente al chasis durante el MVP.

- La pose estimada de la cámara tiene una transformación fija respecto al rover.
- `look_at(target_id)` rota el chasis hasta centrar el target.
- No existe gimbal en el primer corte.
- El diseño permite añadir un gimbal más adelante sin cambiar el significado de
  las herramientas cognitivas.

El celular contiene el núcleo cognitivo y la percepción de alto nivel. El
microcontrolador y los controladores de navegación convierten objetivos en
movimiento físico.

## 3. Principio central

Pulso separa cuerpo y cerebro:

### Cuerpo y reflejos

- Captura RGB, profundidad, IMU y odometría.
- Estima pose mediante VIO.
- Construye el mapa.
- Mantiene tracks de targets.
- Calcula rutas y colisiones.
- Genera opciones físicamente posibles.
- Frena ante peligro inmediato.

### Gemma, núcleo cognitivo

- Mantiene el propósito de misión.
- Formula preguntas e hipótesis.
- Decide qué evidencia necesita.
- Elige qué observar.
- Decide cuándo cargar una skill.
- Elige viewpoints, frontiers y anchors.
- Decide si iluminar, escuchar, hablar o cambiar el plan.
- Relaciona evidencia con objetivos.
- Confirma, revisa o descarta hipótesis.

Si se elimina Gemma, queda un rover capaz de mapear y evitar obstáculos, pero
no un agente capaz de dirigir una misión de búsqueda y evaluación.

## 4. Capas de información

~~~mermaid
flowchart TD
    S["Sensores físicos o simulados"] --> W["WorldState canónico"]
    W --> R["ContextSelector"]
    W --> V["WorldViewRenderer"]
    W --> B["BriefBuilder"]
    G0["Mission y Goal records"] --> B
    H["Hypothesis records de Gemma"] --> B
    C["MissionCheckpoint"] --> P["WorldPacket selectivo"]
    K["SkillContext"] --> P
    R --> P
    V --> P
    B --> P
    P --> G["Gemma 4 E4B · target"]
    G --> T["Tools"]
    T --> W
~~~

### WorldState

Estado canónico completo mantenido fuera del modelo.

### WorldViews

Representaciones visuales derivadas: EgoView, TargetView, MetaView y
CandidateView.

### CognitiveBrief

Proyección textual pequeña del presente, construida desde hechos canónicos y
estado cognitivo estructurado.

### MissionCheckpoint

Memoria histórica creada para reemplazar eventos antiguos compactados.

### WorldPacket

Única entrada dinámica entregada a Gemma. Contiene solo lo necesario para la
decisión actual.

## 5. WorldState canónico

WorldState vive en memoria para lectura rápida. Room/SQLite persiste registros
de misión, eventos, hipótesis, evidencia y checkpoints. Las imágenes, audio y
nubes de puntos se almacenan como artifacts referenciados.

### 5.1 Relojes y secuencias

~~~text
world_seq: 319
sensor_map_seq: 9814
navigation_revision: 27
semantic_revision: 51
tracking_epoch: 3
mission_elapsed: 00:17:26.420
monotonic_now: 1843.720 s
wall_clock: 2026-08-01T14:32:08-05:00
~~~

Significado:

- `world_seq` cambia ante cualquier modificación canónica.
- `sensor_map_seq` puede cambiar con cada integración de profundidad o puntos.
- `navigation_revision` cambia solo cuando se altera materialmente la
  transitabilidad, un corredor, un hazard o la topología local.
- `semantic_revision` cambia cuando un target, fuente de sonido o entidad cambia
  de manera material.
- `tracking_epoch` cambia después de una pérdida o relocalización que pueda
  modificar el marco espacial.

Gemma normalmente no necesita ver todos estos contadores. El ContextSelector
solo incluye los relevantes.

### 5.2 Estado del rover

~~~text
robot:
  pose:
    position_m: [1.82, -0.43, 0.00]
    heading_deg: 31
    confidence: 0.87
    observed_at: 00:17:26.396
  tracking:
    state: TRACKING
    epoch: 3
    quality: 0.91
  motion:
    state: STOPPED
    active_navigation_goal: null
  battery: 73%
  flashlight: OFF
~~~

### 5.3 Mapa y entorno

~~~text
environment:
  explored_area: 34%
  traversable_regions: [...]
  occupied_regions: [...]
  unknown_regions: [...]
  hazards: [...]
  frontiers: [FR-021, FR-022]
  pointcloud_artifact: pointcloud_9814
  occupancy_artifact: occupancy_27
~~~

La nube completa y el mapa denso nunca se serializan al prompt.

### 5.4 Targets y tracks

~~~text
target C03:
  track_revision: 8
  position_3d_m: [2.13, 1.44, 0.38]
  bearing_deg: 31
  range_m: 2.4
  occlusion: 0.68
  detector_beliefs:
    possible_human: 0.76
    fabric_or_object: 0.21
  first_seen: 00:16:41.120
  last_seen: 00:17:24.301
  observation_age: 2.119 s
  confidence: 0.76
  evidence_refs:
    - frame_821
    - target_C03_821
    - depth_C03_821
  validity:
    revalidate_after: 00:17:29
    invalid_if:
      - tracking_epoch_changes
      - target_displacement_gt_0.5m
~~~

La incertidumbre aumenta conforme envejece el track.

### 5.5 Misiones, objetivos e hipótesis

~~~text
mission M-001:
  title: "Localizar y verificar posibles sobrevivientes"
  status: ACTIVE

goal G-007:
  mission_id: M-001
  title: "Confirmar o descartar C03"
  success_condition:
    "Obtener evidencia suficiente para clasificar C03 o declarar
    que no puede verificarse desde posiciones seguras."
  reason:
    "Forma humana parcial y sonido cercano."
  status: ACTIVE
  created_by: GEMMA

hypothesis H-012:
  mission_id: M-001
  goal_id: G-007
  entity_id: C03
  claim: "C03 podría ser una persona atrapada."
  confidence: 0.64
  evidence_refs: [target_C03_821]
  unresolved:
    - "No se observa rostro."
    - "No se confirma movimiento."
  status: OPEN
  created_by: GEMMA
~~~

Reglas:

- Toda hipótesis pertenece a una misión.
- Cuando sea relevante a un objetivo concreto, también contiene `goal_id`.
- `set_mission_focus` crea o actualiza un Goal record y devuelve su ID.
- El goal activo aparece en todos los CognitiveBrief hasta que se complete,
  cancele o reemplace.
- Al cambiar de goal, el anterior conserva su historial y recibe un estado:
  `COMPLETED`, `SUPERSEDED`, `ABANDONED` o `PAUSED`.
- Una hipótesis puede sobrevivir al cambio de goal, pero conserva el vínculo al
  goal que motivó su creación.

### 5.6 Artifacts

~~~text
artifacts:
  frame_914:
    type: EGO_RGB
    captured_at: 00:17:26.201
  target_C03_914:
    type: TARGET_CROP
    entity_id: C03
  metaview_NAV27:
    type: META_VIEW
    navigation_revision: 27
  candidate_VS17:
    type: CANDIDATE_VIEW
    viewpoint_set_id: VS-017
~~~

WorldState guarda referencias, no bytes de imágenes dentro del estado textual.

## 6. Gemma no recibe todo el WorldState

Enviar el estado completo contradice el objetivo de evitar context rot.

`ContextSelector` construye cada WorldPacket usando:

- Misión y goal activos.
- Evento que activó a Gemma.
- Tool result recién producido.
- Targets relacionados con el goal.
- Cambios salientes desde el turno anterior.
- Información solicitada explícitamente por Gemma.
- Skills relevantes.
- Presupuesto de contexto.

### Paquete mínimo normal

~~~text
WORLD PACKET WP-319

TIME
mission_elapsed: 00:17:26

ACTIVE MISSION
M-001 — Localizar y verificar posibles sobrevivientes

ACTIVE GOAL
G-007 — Confirmar o descartar C03

COGNITIVE BRIEF
[texto corto]

TRIGGER
Nueva observación parcial de C03.

RELEVANT ENTITIES
C03 únicamente.

LATEST RESULT
[si existe]

SKILL CONTEXT
[solo catálogo corto y estados relevantes]
~~~

El paquete no incluye automáticamente:

- Point cloud.
- Todos los targets antiguos.
- Todas las rutas.
- Historial completo.
- Imágenes no solicitadas.
- Batería si no afecta la decisión.
- Métricas internas sin significado operativo.
- Skills sin relación razonable con la misión.

## 7. Política multimodal y MetaView bajo demanda

MetaView no se adjunta en todos los turnos.

Se genera y entrega solo cuando Gemma:

1. llama `observe(view="meta")`;
2. llama `propose_viewpoints(...)`;
3. llama `propose_frontiers(...)`; o
4. solicita explícitamente una comparación espacial equivalente.

`propose_viewpoints` y `propose_frontiers` implican una solicitud de MetaView:
su resultado incluye una CandidateView espacial.

EgoView o TargetView pueden adjuntarse automáticamente cuando el evento que
activa a Gemma es visual, por ejemplo un nuevo candidato humano. Aun así, se
adjunta solo la evidencia relevante, no el stream completo.

### 7.1 EgoView

- Imagen actual desde el rover.
- Timestamp y edad.
- Tracking quality.
- Overlays solo cuando ayuden a interpretar.

### 7.2 TargetView

- Crop de un target.
- RGB original.
- Máscara o bounding region.
- Profundidad y confianza si fueron solicitadas.
- Variante low-light o high-contrast si Gemma la pidió.

### 7.3 MetaView

- Rover y orientación.
- Cono de visión.
- Espacio conocido, desconocido y ocupado.
- Targets e incertidumbre.
- Frontiers, viewpoints, anchors y rutas solicitadas.
- Timestamp, escala y estado de validez.

### 7.4 CandidateView

Comparación visual generada por una tool de planificación.

## 8. Diseño visual Tactical MetaView

MetaView tendrá una estética de HUD táctico de alto contraste, inspirada en la
claridad visual de interfaces de videojuegos y anime, sin copiar assets
protegidos.

### Paleta propuesta

~~~text
Fondo conocido:      negro / azul muy oscuro
Desconocido:         niebla violeta grisácea
Obstáculos:          rojo intenso con borde
Rover:               blanco azulado
Cono de visión:      azul eléctrico translúcido
Target prioritario:  naranja brillante con halo
Ruta A:              amarillo neón
Ruta B:              cyan neón
Ruta C:              magenta neón
Ruta seleccionada:   verde neón
Hazard:              rojo pulsante
~~~

El rojo se reserva preferentemente para hazards. Usarlo también para un camino
podría hacer que Gemma y los humanos confundan “opción” con “peligro”.

### Codificación redundante

Gemma nunca elige únicamente por color:

~~~text
Ruta A / VP-017-A / amarillo / línea sólida
Ruta B / VP-017-B / cyan / línea discontinua
Ruta C / VP-017-C / magenta / línea punteada
~~~

Cada ruta tendrá:

- Letra grande.
- ID estable.
- Color neón.
- Patrón de línea.
- Flechas de dirección.
- Card con tiempo, riesgo, visibilidad y validez.
- Leyenda dentro de la imagen.

El tool call utiliza el ID, no el color:

~~~text
move_to(goal_ref="VP-017-B", purpose="Observar el torso de C03")
~~~

Esto permite una visualización impactante y al mismo tiempo robusta para el
modelo.

## 9. CognitiveBrief híbrido y controlado

Gemma no genera libremente todo el CognitiveBrief. Eso permitiría que una
inferencia incorrecta se reescriba como si fuera un hecho.

`BriefBuilder` lo compone determinísticamente desde dos fuentes:

### Fuente A: estado canónico

- Tiempo actual.
- Pose y tracking cuando sean relevantes.
- Misión y goal activos.
- Observaciones y cambios recientes.
- Targets relacionados.
- Validez de datos.
- Tool result actual.
- Evento que requiere una decisión.

### Fuente B: estado cognitivo persistido por Gemma

Gemma contribuye mediante estructuras explícitas:

- `set_mission_focus` crea o cambia el goal activo.
- `update_hypothesis` registra su interpretación.
- El campo `purpose` de sus tool calls registra su intención operativa.
- Preguntas no resueltas quedan vinculadas a hipótesis o goals.

El BriefBuilder convierte ambos conjuntos en lenguaje natural. Gemma aporta su
situación cognitiva, pero no puede transformar unilateralmente una inferencia en
hecho sensorial.

### Formato

~~~text
COGNITIVE BRIEF — WP-319 — 00:17:26

ACTIVE MISSION
M-001 — Localizar y verificar posibles sobrevivientes.

ACTIVE GOAL
G-007 — Confirmar o descartar C03.
Success condition: obtener evidencia suficiente desde posiciones seguras.

CURRENT FACTS
Pulso está detenido y su tracking es confiable.
C03 fue observado por última vez hace 2.1 s a 2.4 m y 31° a la derecha.
El 68% de la región candidata está ocluida.

GEMMA'S CURRENT BELIEF
H-012 — C03 podría ser una persona atrapada — confidence 0.64.
No se observa rostro y no se ha confirmado movimiento.

WHAT CHANGED
Una nueva observación mostró una forma similar a un brazo.

CURRENT INTENT
Determinar si una perspectiva distinta puede revelar torso o rostro.

DECISION TRIGGER
La evidencia actual no resuelve H-012.
~~~

Propiedades:

- Misión y goal activos aparecen siempre con ID.
- Solo incluye targets y hechos relevantes.
- Se regenera después de cada cambio significativo.
- No sustituye las imágenes.
- No contiene historial narrativo innecesario.
- No decide la siguiente acción.

## 10. MissionCheckpoint y compactación

MissionCheckpoint existe específicamente porque parte del historial fue
compactado.

~~~text
MISSION CHECKPOINT MC-004
reason: TOKEN_COMPACTION
created_at: 00:17:20
compacted_through_event: E418
world_seq_at_creation: 314

This checkpoint replaces older interaction history.
It is historical continuity, not current perception.
Current WorldState and current tool results take precedence.
~~~

Contiene:

- Misión y goal activos con IDs.
- Condición de éxito.
- Hipótesis abiertas y resueltas.
- Preguntas pendientes.
- Decisiones importantes.
- Resultados completados.
- Evidencia referenciada.
- Skills relevantes y estado de contexto.
- Último propósito operativo.
- Blockers y próximos puntos de decisión.

No contiene:

- Imágenes embebidas.
- Point cloud.
- Rutas completas obsoletas.
- Coordenadas presentadas como actuales sin timestamp.
- Tool outputs enormes.

### Flujo de compactación

1. ADK detecta el umbral.
2. `PulsoEventSummarizer` extrae hechos estructurados.
3. Se genera MissionCheckpoint.
4. Se conservan los últimos ciclos completos.
5. Toda skill previamente cargada pasa a
   `EVICTED_AFTER_COMPACTION`.
6. En el siguiente turno se adjunta el checkpoint y un WorldPacket actual.
7. Gemma decide si necesita recargar una skill.

Los resultados importantes de tools no dependen del chat:

- Pose y movimiento actualizan WorldState.
- Decisiones actualizan Mission/Goal records.
- Inferencias actualizan Hypothesis records.
- Evidencia queda en ArtifactIndex.
- Resultados de navegación actualizan NavigationGoalStore.

## 11. Skills con política Pulso

Se reutilizan `SkillSource`, formatos SKILL.md y contratos de ADK Kotlin. Se
reemplaza la instrucción genérica agresiva por `PulsoSkillToolset`.

### Catálogo visible

Cada entrada contiene únicamente información útil para decidir si cargarla:

~~~text
visual_survivor_assessment@1
when_to_use:
  Cuando debas decidir qué evidencia visual buscar para verificar
  una posible persona parcial u ocluida.
context_status: EVICTED_AFTER_COMPACTION

low_visibility_observation@1
when_to_use:
  Cuando oscuridad, reflejos o profundidad poco confiable impidan
  interpretar una observación.
context_status: NOT_LOADED

survivor_dialogue@1
when_to_use:
  Cuando exista evidencia suficiente de una posible persona y necesites
  verificar presencia, consciencia o capacidad de responder.
context_status: NOT_LOADED
~~~

No se muestra tamaño estimado en tokens. El runtime puede conocer costos para
presupuestar contexto, pero esa métrica no ayuda a Gemma a dirigir la misión.

### Estados

~~~text
NOT_LOADED
LOADED
EVICTED_AFTER_COMPACTION
OUTDATED_VERSION
~~~

### Política

Gemma carga una skill únicamente cuando:

1. su procedimiento sirve para el goal actual;
2. la siguiente decisión depende de ese procedimiento; y
3. su contenido no está `LOADED`.

No la carga solo por similitud temática.

Después de cargarla:

- la skill aporta conocimiento;
- Gemma elige una tool operativa;
- la skill nunca se devuelve como acción física;
- el runtime registra nombre, versión/hash y evento de carga.

Después de compactar:

- el cuerpo exacto se considera ausente;
- el MissionCheckpoint conserva nombre, versión, pertinencia y estado;
- Gemma decide si recargarla antes de una decisión que dependa de ella.

## 12. Viewpoints, frontiers y navigation goals

### Viewpoint

Es una pose candidata para responder una pregunta sobre un target conocido.

~~~text
target: C03
question: "¿Es una persona?"
desired_evidence: ["torso", "rostro"]
~~~

`propose_viewpoints` genera posiciones alrededor de C03 y estima desde cuál se
obtendría mejor evidencia.

### Frontier

Es una frontera entre espacio conocido y desconocido. No intenta mirar mejor a
un target existente; intenta descubrir una nueva región.

Ejemplos:

- Final de un corredor aún no explorado.
- Entrada parcialmente observada.
- Espacio detrás de una abertura.

`propose_frontiers` genera opciones de exploración y estima:

- área nueva esperada;
- costo de recorrido;
- riesgo;
- posibilidad de retorno;
- señales cercanas;
- relevancia para la misión.

### Anchor

Es un lugar conocido y persistente:

- Punto de inicio.
- Zona segura.
- Última posición confirmada de una persona.
- Punto de comunicación.

### NavigationGoal común

`move_to` no se limita a viewpoints. Acepta una referencia tipada:

~~~text
NavigationGoal:
  VIEWPOINT  -> VP-017-B
  FRONTIER   -> FR-022
  ANCHOR     -> AN-HOME
~~~

Gemma no inventa coordenadas. Obtiene goal IDs de:

- `propose_viewpoints` para active perception;
- `propose_frontiers` para exploración;
- anchors ya presentes en el WorldState.

`look_at` no crea un NavigationGoal: rota el rover en el sitio.

## 13. Validez correcta de viewpoints

Cada nuevo punto de profundidad puede incrementar `sensor_map_seq`, pero eso no
invalida un viewpoint.

Un viewpoint depende de una región espacial concreta:

~~~text
viewpoint VP-017-B:
  set_id: VS-017
  target_id: C03
  question_id: Q-019
  created_at: 00:17:26
  tracking_epoch: 3
  target_track_revision: 8
  route_corridor: RC-044
  visibility_region: VR-012
  navigation_revision_at_creation: 27
  revalidate_after: 00:17:36
  state: FRESH
~~~

### Estados de validez

~~~text
FRESH
REVALIDATION_REQUIRED
INVALID
CONSUMED
~~~

### No lo invalida

- Un punto nuevo en otra habitación.
- Refinamiento pequeño de una pared que no afecta ruta ni visibilidad.
- Incremento de `world_seq` por batería o audio no relacionado.
- Nueva evidencia de otro target.

### Requiere revalidación

- Pasó `revalidate_after`.
- Cambió la geometría dentro del corredor.
- Cambió materialmente la oclusión prevista.
- La posición de C03 se ajustó.
- Bajó la calidad de tracking.

### Lo invalida

- Apareció un obstáculo en su ruta.
- C03 se movió fuera de la tolerancia.
- Hubo relocalización y cambió `tracking_epoch`.
- La posición dejó de ser transitable.
- El objetivo o pregunta fueron cancelados.

Antes de `move_to` se ejecuta una validación just-in-time:

~~~text
validate_navigation_goal(VP-017-B)
~~~

Si sigue bien, se ejecuta. Si necesita revalidación, se recalculan sus métricas.
Solo si falla se devuelve `INVALID` a Gemma.

## 14. Active perception híbrida

### Paso 1: Gemma formula la pregunta

~~~text
Q-019
goal_id: G-007
target_id: C03
question: "¿C03 es una persona?"
desired_evidence:
  - torso
  - rostro
  - movimiento voluntario
~~~

### Paso 2: Gemma solicita opciones

~~~text
propose_viewpoints(
  target_id="C03",
  question="¿C03 es una persona?",
  desired_evidence=["torso", "rostro", "movimiento"],
  preference="conservar ruta segura de retirada"
)
~~~

### Paso 3: determinismo restringe la física

El generador:

- muestrea poses;
- elimina colisiones;
- comprueba transitabilidad;
- proyecta el campo de visión;
- estima oclusión sobre geometría conocida;
- calcula tiempo, riesgo e información esperada.

No genera una imagen futura realista de regiones que el robot todavía no ha
visto. Solo muestra predicción geométrica basada en conocimiento disponible.

### Paso 4: multimodalidad ayuda a Gemma

Gemma recibe CandidateView con:

- MetaView de rutas;
- crop actual de C03;
- visibilidad esperada;
- incertidumbre;
- tiempo y riesgo;
- IDs de cada opción.

### Paso 5: Gemma selecciona

La elección es semántica:

~~~text
move_to(
  goal_ref="VP-017-B",
  purpose="Buscar torso y rostro para resolver H-012"
)
~~~

### Paso 6: evidencia real

Al llegar se produce una nueva observación. Gemma decide si:

- responde Q-019;
- actualiza H-012;
- solicita otra perspectiva;
- ilumina;
- habla;
- abandona la hipótesis.

Un viewpoint predice utilidad. No responde una pregunta hasta que existe una
observación real desde él.

## 15. Superficie de tools V0.2

### Conocimiento

#### `load_skill(skill_name)`

Carga instrucciones de una skill cuando la siguiente decisión depende de ellas.

#### `load_skill_resource(skill_name, path)`

Carga una referencia de una skill ya seleccionada.

### Percepción

#### `observe(view, target_id?, purpose?, processing?)`

~~~text
view:
  ego | target | meta | depth | candidate

processing:
  original | low_light | high_contrast | depth_overlay
~~~

`observe(view="meta")` es una solicitud explícita de MetaView.

#### `look_at(target_id, purpose)`

Rota el chasis hasta centrar un target vigente.

#### `listen(duration, target_id?, purpose)`

Captura audio y produce observaciones o transcripción.

### Active perception y exploración

#### `propose_viewpoints(target_id, question, desired_evidence, preference?)`

Genera opciones para observar mejor un target conocido. Devuelve CandidateView.

#### `propose_frontiers(objective, preference?)`

Genera opciones para descubrir espacio desconocido. Devuelve CandidateView.

### Movimiento

#### `move_to(goal_ref, purpose)`

Acepta `VIEWPOINT`, `FRONTIER` o `ANCHOR`. Revalida antes de ejecutar.

#### `stop_motion(reason)`

Detiene voluntariamente la navegación. Los reflejos físicos también pueden
detenerla.

### Entorno

#### `set_illumination(mode, purpose)`

~~~text
torch_on | torch_off | auto
~~~

El contraste es una variante de `observe`, no iluminación física.

### Comunicación

#### `speak(text, purpose)`

Habla mediante TTS.

### Cognición persistente

#### `set_mission_focus(mission_id, goal, success_condition, reason)`

Crea un Goal record, lo activa y devuelve `goal_id`.

#### `update_hypothesis(mission_id, goal_id?, entity_id?, claim, confidence, evidence_refs, unresolved?, status?)`

Crea o actualiza una hipótesis vinculada a misión y, cuando corresponda, goal y
entidad.

## 16. Ciclo del agente

### Loops continuos

- Sensores y VIO: alta frecuencia.
- Seguridad y control: alta frecuencia.
- Detector, tracker y mapa: frecuencia de percepción.
- Gemma: event-driven.

### Triggers cognitivos

- Nuevo target.
- Nueva evidencia importante.
- Viewpoint alcanzado.
- Frontier alcanzado.
- Ruta bloqueada.
- Tracking degradado.
- Persona respondió.
- Hipótesis no resuelta.
- Goal expiró o quedó imposible.
- Tool terminó.
- Contexto fue compactado.

### Turno cognitivo

1. WorldState recibe el evento.
2. ContextSelector determina qué importa.
3. BriefBuilder genera CognitiveBrief.
4. WorldViewRenderer adjunta solo vistas solicitadas o necesarias.
5. MissionCheckpoint se adjunta si existe.
6. SkillContext publica catálogo y estados relevantes.
7. Gemma llama una tool.
8. La tool actualiza estado y artifacts.
9. Un nuevo evento decide si Gemma debe continuar.

## 17. System prompt V0.2

~~~text
Eres el núcleo cognitivo de Pulso, un sistema físico autónomo para
explorar espacios afectados, localizar posibles sobrevivientes y obtener
evidencia útil para su rescate.

Tu función es mantener el propósito de misión, formular y revisar hipótesis,
decidir qué información falta, seleccionar objetivos y utilizar herramientas
para actuar en el mundo.

WORLD PACKET

No recibes el WorldState completo. Cada turno recibes un WorldPacket selectivo
con solo la información relevante para la decisión actual.

Un WorldPacket puede contener:

- ActiveMission y ActiveGoal con IDs.
- CognitiveBrief.
- EgoView o TargetView cuando el evento sea visual.
- MetaView o CandidateView solo cuando la hayas solicitado mediante observe
  o una herramienta de planificación espacial.
- MissionCheckpoint.
- SkillContext.
- RecentEvents y el tool result más reciente.

MISSION Y GOALS

Mantén una misión activa y un goal operativo con condición de éxito.
set_mission_focus crea o cambia el goal y devuelve un goal_id.
El goal activo seguirá apareciendo en CognitiveBrief hasta que se complete,
pause, abandone o reemplace.

Relaciona las hipótesis con mission_id y, cuando correspondan a un objetivo
concreto, también con goal_id.

MISSION CHECKPOINT

MissionCheckpoint existe porque eventos anteriores fueron compactados.
Es continuidad histórica, no percepción actual. Puede estar desactualizado.
El WorldState proyectado en el CognitiveBrief y los tool results actuales
tienen prioridad.

Después de una compactación, una skill previamente cargada puede aparecer como
EVICTED_AFTER_COMPACTION. Eso significa que su nombre y pertinencia se
recuerdan, pero sus instrucciones exactas ya no están disponibles.

TIEMPO Y VALIDEZ

Considera timestamps, edad y condiciones de validez.
No asumas que world_seq o sensor_map_seq hacen obsoleto un objetivo.
Un viewpoint o frontier solo requiere revalidación cuando cambian su corredor,
la geometría relevante, el target, el tracking o su condición temporal.

Usa siempre IDs vigentes. move_to revalida el goal antes de ejecutarlo.

EVIDENCIA

Distingue:

- hechos sensoriales o geométricos;
- resultados de detectores;
- tus hipótesis;
- información desconocida.

Las métricas de un viewpoint son predicciones de utilidad, no observaciones.
Una pregunta solo puede considerarse respondida después de obtener evidencia
real desde la nueva posición.

Cuando una hipótesis cambie, persístela con update_hypothesis y relaciónala con
su misión, goal, entidad y evidencia.

CICLO DE DECISIÓN

En cada ciclo:

1. Revisa ActiveMission, ActiveGoal y cambios recientes.
2. Identifica la incertidumbre que más afecta el goal.
3. Decide si puedes actuar con la evidencia presente o necesitas observar,
   cargar conocimiento, cambiar perspectiva, explorar, iluminar, escuchar o
   comunicarte.
4. Selecciona una tool cuyo resultado pueda avanzar el goal.
5. Incluye un propósito breve y observable.
6. Después del resultado, revisa goal e hipótesis.

Prefiere una acción significativa por vez cuando su resultado pueda cambiar la
siguiente decisión.

SKILLS

Las skills son conocimiento procedimental, no acciones físicas.

Cada skill incluye when_to_use y context_status.
Carga una skill únicamente cuando:

- sea útil para ActiveGoal;
- la siguiente decisión dependa de sus instrucciones; y
- su estado no sea LOADED.

No la cargues solo por similitud temática.
Si aparece EVICTED_AFTER_COMPACTION, decide si necesitas recargarla antes de
actuar. Después de leerla, utiliza una tool operativa.

TOOLS

- observe obtiene una vista fresca. Usa view=meta solo cuando necesites una
  representación cenital.
- look_at centra un target rotando el chasis.
- propose_viewpoints sirve para responder una pregunta sobre un target conocido.
- propose_frontiers sirve para descubrir espacio todavía desconocido.
- move_to acepta un VIEWPOINT, FRONTIER o ANCHOR vigente.
- set_illumination modifica la luz física.
- speak y listen permiten interacción.
- set_mission_focus cambia el goal operativo.
- update_hypothesis conserva tus inferencias vinculadas a misión y evidencia.

METAVIEW

Las rutas aparecen con color, letra e ID. Usa siempre el ID.
El color es una ayuda visual, no la identidad de la ruta.
Hazards y regiones desconocidas no son rutas transitables.

EXPLICABILIDAD

Cada tool operativa debe incluir un propósito corto que pueda mostrarse en la
interfaz. No produzcas una narración extensa de razonamiento interno.
~~~

## 18. Persistencia propuesta

### En memoria

- WorldState actual.
- TargetTracker.
- NavigationGoalStore.
- Viewpoint y Frontier sets vigentes.
- SkillContextState.
- Artifact handles recientes.

### Room/SQLite

- MissionRecord.
- GoalRecord.
- HypothesisRecord.
- EventLog.
- MissionCheckpoint.
- ArtifactIndex.
- Skill version/hash y cargas.
- Resultados importantes de navegación.

### Archivos

- Imágenes.
- Audio.
- Map snapshots.
- Point clouds.
- Session recordings.

## 19. Invariantes de diseño

1. Gemma nunca recibe el WorldState completo.
2. MetaView es bajo demanda.
3. Ninguna imagen del simulador puede contener ground truth no observable.
4. Una hipótesis nunca se presenta como hecho sensorial.
5. Una ruta se identifica por ID, no solo por color.
6. Un viewpoint no se invalida por cambios irrelevantes del mapa.
7. Toda navegación se revalida justo antes de ejecutarse.
8. Toda hipótesis pertenece a una misión.
9. El goal activo siempre aparece con ID en CognitiveBrief.
10. MissionCheckpoint se identifica como memoria de compactación.
11. Una skill compactada se considera expulsada hasta recargarse.
12. El cuerpo garantiza control y reflejos; Gemma dirige la misión.

## 20. Decisiones congeladas en V0.2

1. Teléfono fijo al chasis en el MVP.
2. Gemma 4 E4B residente y multimodal como target; promoción en host/simulación
   satisfecha y gate S25 separado.
3. WorldState canónico fuera del modelo.
4. ContextSelector para relevancia y presupuesto.
5. CognitiveBrief híbrido pero ensamblado determinísticamente.
6. MetaView y CandidateView bajo demanda.
7. Tactical MetaView con codificación visual redundante.
8. Viewpoints para active perception.
9. Frontiers para exploración.
10. `move_to` con referencias tipadas.
11. Validez espacial, temporal y por dependencias.
12. Misión, goal e hipótesis relacionados por IDs.
13. MissionCheckpoint ligado explícitamente a compactación.
14. `PulsoSkillToolset` con carga selectiva.
15. Catálogo de skills sin tamaños de tokens.
16. Superficie de tools y system prompt definidos en este documento.
