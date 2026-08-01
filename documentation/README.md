# PULSO — documentación

## Ruta recomendada

1. [Guía visual de cinco minutos](visual/README.md)
2. [Qué existe y cómo fluye de sensor a acción](PULSO_SYSTEM_ARCHITECTURE.md)
3. [Cómo arrancar, mirar y operar todo](PULSO_OPERATOR_MANUAL.md)
4. [Referencia de tópicos y contratos](PULSO_TOPIC_REFERENCE.md)
5. [Cómo probar, diagnosticar y recuperar](PULSO_VERIFICATION_AND_RECOVERY.md)
6. [Validación final y operación de entrega](evidence/FINAL_VALIDATION.md)

El [runbook corto](PULSO_IMPLEMENTATION_RUNBOOK.md) reúne únicamente los
comandos principales para una demo.

Flujo portable desde la raíz del checkout:

```bash
./pulso install
./pulso doctor
./pulso sim
./pulso stop
./pulso real --dry-run
```

El `stop` es obligatorio al cambiar de `sim` a `real`. `PULSO_DATA_ROOT` es un
override opcional; el valor por defecto no exige un disco externo. En la app,
el botón físico vigente es `CONECTAR S25`. Mission Control conserva
`/pulso/phone/telemetry` y `/pulso/phone/rgb/camera_info` como evidencia
recibida, nunca como validación implícita.

Decisión de modelo vigente: **Gemma 4 E4B** es el target. Su artefacto/hash,
perfil nativo, APK y E2E estricto sin mocks ya están preservados. Los resultados
E2B permanecen solo como baseline histórico; la instalación y medición en S25
no se infieren del build. `ANDROID_REAL` ya implementa RGB/Depth/VIO/IMU,
torch, audio/TTS y E4B local; `pulso real` repite el preflight en cada sesión.
El corte posterior valida la cognición S25 en HIL. La validación física de
ARCore `TRACKING`, nube y térmica sostenida sigue pendiente de confirmación
Atlas. La locomoción Zeus permanece no validada.

## Diseño cognitivo

- [V0.2 — especificación vigente](PULSO_COGNITIVE_ARCHITECTURE_V0.2.md)
- [V0.1 — corte aprobado original](PULSO_COGNITIVE_ARCHITECTURE_V0.1.md)

V0.2 es canónico para WorldState, WorldPacket, CognitiveBrief,
MissionCheckpoint, skills, tools y active perception. Los manuales operativos
describen qué parte de ese diseño está ejecutada hoy y señalan lo pendiente.

## Seguridad y modelos

- [Proveniencia y benchmark de modelos](MODEL_PROVENANCE.md)
- [Threat model y límite de seguridad física](PULSO_THREAT_MODEL.md)

## Simulación relacionada

- [Contrato de sensores](../docs/simulation/SENSOR_CONTRACT.md)
- [Alcance del rover](../docs/simulation/ROBOT_SCOPE.md)
- [Fuentes de simulación](../docs/simulation/SOURCES.md)
