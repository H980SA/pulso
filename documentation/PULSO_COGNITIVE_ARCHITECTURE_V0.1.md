# Pulso: arquitectura cognitiva V0.1

> Documento histórico. La implementación vigente añade `ANDROID_REAL` para
> RGB/Depth/VIO/IMU, torch y audio/TTS en S25. Esa ruta está implementada pero
> espera validación runtime; la locomoción Zeus permanece bloqueada.

Estado: corte aprobado original.  
Fecha: 2026-07-31.  
Reemplazada como especificación vigente por V0.2.

Nota histórica: V0.1 fijó E2B. El target vigente desde 2026-08-01 es E4B; no se
edita el diagrama original porque documenta la decisión anterior, y tampoco se
usa como evidencia de validación E4B.

## 1. Decisión física inicial

El Samsung S25 estará fijo horizontalmente al chasis.

Esto simplifica:

- La pose estimada del celular representa directamente el movimiento del rover.
- `look_at(C03)` hará girar el chasis sobre su eje hasta centrar a C03.
- No necesitamos calcular la relación cambiante entre gimbal, teléfono y rover.
- Más adelante se puede añadir un gimbal sin cambiar la interfaz cognitiva.

El ESP32 o controlador ejecutará los motores. Gemma decide el objetivo; el
controlador convierte ese objetivo en velocidades.

## 2. Las cinco capas de información

~~~mermaid
flowchart TD
    S["Sensores físicos o simulados"] --> W["WorldState canónico"]
    W --> V["WorldViews: EgoView y MetaView"]
    W --> B["CognitiveBrief"]
    W --> P["WorldPacket multimodal"]
    V --> P
    B --> P
    C["MissionCheckpoint"] --> P
    K["Skills y estado de contexto"] --> P
    P --> G["Gemma 4 E2B"]
    G --> T["Tools"]
    T --> S
~~~

### WorldState

Es la verdad operativa actual mantenida por software.

### WorldViews

Son imágenes generadas a partir de esa verdad: cámara, mapa cenital, crops y
profundidad.

### CognitiveBrief

Es la explicación corta y masticada de la situación actual.

### MissionCheckpoint

Es memoria histórica creada porque parte del historial fue compactada.

### WorldPacket

Es el paquete multimodal concreto que Gemma recibe en una decisión.

Gemma no recibe todo el WorldState crudo. Recibe una proyección relevante:
el WorldPacket.

## 3. Qué contiene el WorldState

El WorldState vive fuera del modelo, en memoria rápida. Los eventos importantes
y snapshots se persistirán con Room/SQLite.

### Identidad temporal

~~~text
world_version: 319
map_version: 143
generated_at_monotonic: 1843.72 s
mission_elapsed: 00:17:26
wall_clock: 2026-08-01T14:32:08-05:00
~~~

Se utilizará tiempo monotónico para calcular edades y expiraciones, hora real
para auditoría y replay, y versiones para detectar decisiones obsoletas.

### Estado del rover

~~~text
pose:
  posición: [1.82, -0.43, 0.00]
  orientación: 31°
  confidence: 0.87

tracking:
  state: TRACKING
  age: 24 ms

motion:
  state: STOPPED
  active_goal: null

battery: 73%
flashlight: OFF
~~~

### Mapa y entorno

~~~text
explored_area: 34%
traversable_regions: [...]
occupied_regions: [...]
unknown_regions: [...]
frontiers: [F01, F02, F03]
hazards: [...]
pointcloud_revision: 143
~~~

La nube de puntos completa no entra al contexto de Gemma. Permanece en el
sistema de mapas.

### Entidades y posibles sobrevivientes

~~~text
C03:
  hypotheses:
    - possible_human: 0.76
    - fabric_or_object: 0.21

  position_3d: [2.13, 1.44, 0.38]
  bearing: 31° derecha
  range: 2.4 m
  occlusion: 68%

  first_seen: 00:16:41
  last_seen: 00:17:24
  observation_age: 2.1 s
  confidence: 0.76

  evidence:
    - frame_821
    - crop_C03_821
    - depth_region_821

  validity:
    expires_at: 00:17:34
    invalid_if:
      - tracking_lost
      - target_displacement_gt_0.5m
~~~

La confianza se reduce conforme envejece una observación.

### Navegación

~~~text
current_route: null
current_frontier: F02
viewpoint_sets: [VS17]
recently_blocked_routes: [...]
~~~

### Hipótesis de Gemma

Las interpretaciones de Gemma no se mezclan con hechos sensoriales:

~~~text
model_hypothesis H12:
  entity: C03
  claim: "Podría ser una persona atrapada."
  confidence: 0.64
  supporting_evidence: [crop_C03_821]
  unresolved:
    - "No se observa rostro."
    - "No se confirma movimiento."
~~~

Así se distingue lo medido, lo detectado por modelos especializados y lo
inferido por Gemma.

## 4. Time awareness

Todo dato temporal tendrá, cuando corresponda:

~~~text
observed_at
age
expires_at
source_timestamp
valid_if
world_version
map_version
~~~

Un viewpoint no expira únicamente por segundos. También se invalida si cambia
algo importante.

~~~text
V2:
  created_at: 00:17:26
  expires_at: 00:17:36
  generated_from_map: 143
  generated_from_target_observation: C03@frame_821

  valid_if:
    - map_version <= 145
    - C03 displacement < 0.4 m
    - tracking == TRACKING
    - route remains traversable
~~~

Antes de ejecutar `move_to(V2)`, la herramienta valida de nuevo las condiciones.

## 5. Viewpoints: multimodalidad, determinismo y Gemma

Un viewpoint propuesto no responde todavía la pregunta de Gemma. Solo predice
desde dónde es más probable obtener la evidencia necesaria.

### Paso 1: Gemma formula una pregunta

~~~text
Pregunta activa:
¿C03 es realmente una persona?

Evidencia que falta:
Una vista más completa del torso o rostro.
~~~

Gemma llama:

~~~text
propose_viewpoints(
  target_id = "C03",
  question = "¿Es una persona?",
  desired_evidence = ["torso", "rostro", "movimiento"],
  preference = "mantener una ruta segura de retirada"
)
~~~

### Paso 2: el módulo determinista genera opciones

El `ViewpointGenerator`:

1. Toma la posición estimada de C03.
2. Examina la nube de puntos y el mapa transitable.
3. Muestrea posiciones posibles alrededor.
4. Descarta posiciones físicamente inaccesibles.
5. Traza rutas.
6. Hace raycasting sobre la geometría conocida.
7. Estima visibilidad, oclusión, distancia, riesgo, tiempo y región desconocida.

No utiliza ground truth del simulador.

### Paso 3: genera una Candidate MetaView

Gemma recibe una imagen con el rover, C03, los viewpoints, caminos, obstáculos,
zona desconocida y campo visual esperado.

~~~text
V1:
  arrival: 0 s
  expected_visibility: 31%
  expected_evidence: ["brazo"]
  information_gain: bajo

V2:
  arrival: 4.2 s
  expected_visibility: 79%
  expected_evidence: ["torso", "posible rostro"]
  information_gain: alto
  risk: bajo

V3:
  arrival: 2.8 s
  expected_visibility: 62%
  unknown_route_fraction: 23%
  information_gain: medio
~~~

### Paso 4: Gemma elige

Gemma combina la pregunta, imágenes, riesgo, tiempo, objetivo y otras señales:

~~~text
move_to(
  goal_ref = "V2",
  purpose = "Obtener una vista del torso y rostro de C03"
)
~~~

### Paso 5: al llegar obtiene la respuesta real

Solo una observación tomada desde el viewpoint puede confirmar o refutar la
hipótesis.

El determinismo calcula qué es físicamente posible y qué probablemente se
verá. Gemma decide qué pregunta importa, qué evidencia necesita, qué viewpoint
vale la pena y si la nueva observación responde la pregunta.

## 6. WorldViews: la MetaVision de Pulso

Desde la perspectiva de Gemma, el WorldState será multimodal.

### EgoView

Imagen real de la cámara en primera persona con timestamp, tracking quality y,
cuando sea relevante, máscaras o profundidad.

### MetaView

Mapa cenital construido con sensores:

- Posición y orientación del rover.
- Cono de visión.
- Trayectoria recorrida.
- Obstáculos y espacio transitable.
- Regiones desconocidas.
- Targets e incertidumbre.
- Fuentes de sonido.
- Frontiers.
- Viewpoints y rutas.

### TargetView

Crop de un objetivo con RGB original, posibles variantes de procesamiento,
máscara, profundidad, edad y confianza.

### CandidateView

Vista gráfica para comparar rutas o viewpoints.

Las imágenes se guardan como artifacts:

~~~text
metaview_319.png
egoview_914.jpg
target_C03_914.jpg
candidate_viewpoints_VS17.png
~~~

WorldState conserva referencias. El WorldPacket adjunta solo las imágenes
necesarias para esa decisión. Después de compactar se regenera la MetaView
actual y se reatacha la evidencia necesaria.

## 7. CognitiveBrief

El CognitiveBrief no es memoria ni resumen del chat. Es una descripción
determinista, corta y natural, generada desde el WorldState actual.

Debe responder:

1. Qué está pasando ahora.
2. Qué cambió desde la última decisión.
3. Cuál es el objetivo activo.
4. Qué incertidumbres importan.
5. Por qué Gemma está siendo invocada.

~~~text
COGNITIVE BRIEF — world 319 — mission 00:17:26

Pulso está detenido y localiza correctamente su posición.
Desde la última decisión apareció C03, un posible humano a 2.4 m
y 31° a la derecha. Solo se observa una forma parecida a un brazo;
el 68% permanece ocluido por una losa.

El objetivo activo es confirmar o descartar C03.
La observación tiene 2.1 segundos de antigüedad y sigue siendo válida.

Hay una ruta de retirada conocida. No existe todavía un conjunto
vigente de viewpoints para C03.

Decisión requerida:
Determinar si la evidencia actual basta o si se necesita una nueva
perspectiva, iluminación o comunicación.
~~~

El CognitiveBrief no elige por Gemma, no inventa explicaciones, no contiene
todo el mapa, no repite el historial y no sustituye las imágenes.

## 8. WorldPacket

Cada decisión puede recibir:

~~~text
WORLD PACKET 319

A. CURRENT TIME
Mission elapsed, timestamps y deadline.

B. COGNITIVE BRIEF
Situación actual.

C. MULTIMODAL VIEWS
EgoView, MetaView y TargetViews relevantes.

D. MISSION CHECKPOINT
Cuando exista historial compactado o continuidad relevante.

E. SKILL CONTEXT
Catálogo y estado de skills relevantes.

F. RECENT COMPLETE EVENTS
Decisión → tool call → resultado → cambio del mundo.

G. TOOL DEFINITIONS
Herramientas y schemas.

H. SALIENT CHANGES
Cambios desde el WorldPacket anterior.
~~~

Gemma permanece cargada durante la misión y se invoca ante eventos relevantes,
no por cada frame.

## 9. MissionCheckpoint y compactación

El MissionCheckpoint existe porque historial antiguo fue compactado.

~~~text
MISSION CHECKPOINT
reason: TOKEN_COMPACTION
created_at: 00:17:20
compacted_through_event: E418
world_version_at_creation: 314

Este checkpoint reemplaza historial anterior.
Es memoria histórica y puede estar desactualizado.
El WorldState actual siempre tiene prioridad.
~~~

Conserva misión, subobjetivo, hechos conocidos, hipótesis, trabajo completado,
preguntas no resueltas, skills relevantes, última acción y referencias de
evidencia.

Reglas:

- Conserva continuidad, no estado actual.
- WorldState actual gana ante contradicciones.
- Las imágenes se referencian, no se resumen.
- Los resultados importantes se incorporan al estado canónico.
- Se conserva una cola de ciclos completos.
- Nunca se separa una tool call de su resultado.
- Después de compactar, skills cargadas pasan a `EVICTED`.

## 10. Skills con ADK Kotlin

Se aprovechará `SkillSource` de ADK Kotlin, reemplazando la política agresiva
de cargar cualquier skill que parezca relevante por `PulsoSkillToolset`.

### Catálogo corto

~~~text
visual_survivor_assessment@1
Cuándo sirve: verificar si una forma parcialmente visible puede ser humana.
Tamaño estimado: 760 tokens.

low_visibility_observation@1
Cuándo sirve: observar cuando oscuridad, reflejos o profundidad pobre
impiden una evaluación.

survivor_dialogue@1
Cuándo sirve: conversar con una posible persona atrapada.
~~~

### Estados

~~~text
NOT_LOADED
LOADED
EVICTED_AFTER_COMPACTION
OUTDATED_VERSION
~~~

Gemma carga una skill solo cuando la siguiente decisión depende del
procedimiento. Después de compactar decide si necesita recargarla.

## 11. Superficie inicial de tools

### Contexto

- `load_skill(skill_name)`
- `load_skill_resource(skill_name, path)`

### Percepción

- `observe(view, target_id?, purpose?, processing?)`
- `look_at(target_id)`
- `listen(duration, target_id?)`

### Active perception

- `propose_viewpoints(target_id, question, desired_evidence, preference?)`
- `propose_frontiers(objective, preference?)`

### Movimiento

- `move_to(goal_ref, purpose)`
- `stop_motion(reason)`

### Entorno

- `set_illumination(mode, purpose)`

### Comunicación

- `speak(text, purpose)`
- `listen(...)`

### Cognición persistente

- `set_mission_focus(goal, success_condition, reason)`
- `update_hypothesis(entity_id, claim, confidence, evidence_refs, unresolved?)`

## 12. System prompt V0.1

~~~text
Eres el núcleo cognitivo de Pulso, un sistema físico autónomo para
explorar espacios afectados, localizar posibles sobrevivientes y obtener
evidencia útil para su rescate.

Tu función es mantener el propósito de misión, interpretar observaciones,
formular y revisar hipótesis, decidir qué información falta, seleccionar
objetivos y utilizar herramientas para actuar en el mundo.

ENTRADAS

Cada ciclo puede incluir un WORLD_PACKET con:

- CognitiveBrief: descripción actual derivada del WorldState.
- EgoView: imagen actual desde el rover.
- MetaView: representación cenital construida únicamente con sensores.
- TargetView: evidencia visual de una entidad.
- CandidateView: comparación de viewpoints o rutas.
- MissionCheckpoint: memoria histórica producida por compactación.
- SkillContext: catálogo y estado de skills.
- RecentEvents: ciclos recientes completos de acción y resultado.

El WorldState actual y los tool results actuales tienen prioridad sobre
MissionCheckpoint. MissionCheckpoint existe para conservar continuidad
después de que eventos anteriores fueron compactados; puede contener
información desactualizada y nunca debe tratarse como observación presente.

TIEMPO Y VALIDEZ

Considera la edad, expiración, versión del mapa y condiciones de validez de
cada dato. Una observación antigua no equivale a una observación presente.
Antes de utilizar un viewpoint o destino, verifica que siga vigente. Si está
obsoleto, solicita opciones nuevas.

EVIDENCIA E HIPÓTESIS

Distingue siempre:

- hecho sensorial o geométrico;
- resultado de un detector;
- inferencia propia;
- información desconocida.

Las métricas esperadas de un viewpoint son predicciones, no observaciones.
Una pregunta solo puede considerarse respondida después de llegar al
viewpoint y obtener evidencia real.

Cuando una conclusión de misión cambie, persístela con update_hypothesis,
incluyendo evidencia y preguntas aún no resueltas.

CICLO DE DECISIÓN

En cada ciclo:

1. Revisa el objetivo activo y los cambios recientes.
2. Determina cuál es la incertidumbre más importante para la misión.
3. Decide si la evidencia actual permite actuar o si necesitas observar,
   iluminar, escuchar, comunicarte o cambiar de perspectiva.
4. Revisa si necesitas conocimiento especializado.
5. Elige la siguiente herramienta que mejor avance el objetivo o reduzca
   una incertidumbre relevante.
6. Después del resultado, revisa tu hipótesis y continúa.

Selecciona una acción significativa por vez cuando su resultado pueda
cambiar la siguiente decisión.

POLÍTICA DE SKILLS

Las skills son conocimiento procedimental, no acciones físicas.

Carga una skill únicamente cuando:

- sea pertinente al objetivo actual;
- la siguiente decisión dependa de sus instrucciones;
- y su estado no sea LOADED.

No cargues una skill solo porque su tema sea parecido a la situación.
Si aparece como EVICTED_AFTER_COMPACTION, decide si necesitas recargarla
antes de continuar. Después de leer una skill, ejecuta la acción apropiada
mediante una herramienta operativa.

POLÍTICA DE HERRAMIENTAS

- Usa observe cuando necesites evidencia visual fresca o una representación
  distinta de la información disponible.
- Usa look_at para centrar un target conocido; con el montaje inicial esto
  rota el chasis.
- Usa propose_viewpoints cuando una oclusión, distancia o perspectiva impida
  responder una pregunta.
- Formula en propose_viewpoints la pregunta y evidencia que quieres obtener.
- Usa propose_frontiers para comparar regiones desconocidas que puedan
  avanzar la exploración.
- Usa move_to solamente con referencias vigentes e indica el propósito.
- Usa set_illumination cuando la luz limite la evidencia.
- Usa speak y listen para verificar presencia o comunicarse con una persona.
- Usa set_mission_focus cuando cambie el subobjetivo operativo.
- Usa update_hypothesis cuando cambie una inferencia importante.

El sistema de mapas, navegación y control convierte tus objetivos en
movimientos físicos. Tú decides el propósito, el destino, la evidencia
necesaria y cuándo revisar el plan.

EXPLICABILIDAD

Cada acción operativa debe incluir un propósito breve y observable para que
la interfaz pueda mostrar qué intenta conseguir Pulso. No generes una
explicación extensa ni una narración de razonamiento interno.
~~~

## 13. Centralidad de Gemma

Gemma decide qué investigar, cuál es la pregunta activa, qué evidencia falta,
qué skill necesita, si debe mirar, iluminar, escuchar o hablar, qué viewpoint
elegir, qué frontier explorar, cuándo confirmar o descartar una hipótesis,
cuándo cambiar el subobjetivo y cómo reaccionar ante información inesperada.

Los módulos deterministas calculan pose, rutas posibles, tiempo, obstáculos,
visibilidad esperada, control motor y frenado inmediato.

Si se elimina Gemma, queda un vehículo que mapea, detecta y evita colisiones,
pero no un agente de búsqueda y evaluación.
