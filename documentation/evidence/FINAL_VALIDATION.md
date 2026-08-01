# PULSO — validación final y operación de entrega

Estado de evidencia: 2026-08-01. Este documento separa lo observado de lo que
sigue abierto y fija la secuencia reproducible para la ejecución de 2026-08-02.

## 1. Qué quedó validado

### Cerebro S25 en HIL

`./pulso sim` usa el S25 como único cerebro por defecto. En la prueba preservada:

- Gemma 4 E4B cargó con GPU en **11.385 s**;
- el ciclo HIL real tardó **56.937 s de extremo a extremo**, incluida la espera
  del resultado de acción; no es una cifra de inferencia pura;
- Gemma propuso un ID de target no canónico y el runtime lo resolvió de forma
  segura al candidato vigente;
- `MOVE_TO` fue aceptado;
- el SafetyGate detectó un obstáculo y bloqueó el movimiento.

La cadena probada es: observación/candidatos reales de Gazebo → contexto S25 →
E4B → tool tipada → canonicalización → acción aceptada → veto de seguridad.

### Preflight físico

La ejecución `real` verificó:

- APK de entrega y modelo E4B en host/teléfono;
- cámara disponible y permisos;
- bridge loopback y `adb reverse`;
- arranque de la app y telemetría observacional.

No se obtuvo ARCore `TRACKING` ni nube física: el S25 permaneció inmóvil y la
cámara no estuvo expuesta al entorno. Esto no es un fallo convertido en éxito;
es un gate pendiente para la próxima sesión supervisada.

Zeus no se movió. Se mantuvo en dry-run y su locomoción sigue **sin validar**.

## 2. Artefacto y pruebas

| Evidencia | Resultado final |
| --- | --- |
| APK | 225609468 bytes |
| APK SHA-256 | `949bae5458233e4b675b01c1b0d46ba2bc797442d0fa772a42cc0fddd59e19b0` |
| Android | 74 tests + `assembleDebug` + lint |
| Mission Control | 27 tests JS + 6 tests Python |
| Brain host | 32 tests |
| E2E | 9 tests |

Estos conteos prueban el corte de software. No sustituyen la evidencia física
pendiente de ARCore, nube, térmica o locomoción.

## 3. Instalación y diagnóstico en Ubuntu

Ejecutar desde la raíz del checkout en Ubuntu 22.04:

```bash
cd /ruta/al/checkout/HACKATHON_ESAN
./pulso install
./pulso doctor
adb devices -l
```

`PULSO_DATA_ROOT` es opcional. Si no se define, Pulso usa
`${XDG_DATA_HOME:-$HOME/.local/share}/pulso`.

## 4. Demo principal: S25 como cerebro de Gazebo

```bash
./pulso stop
./pulso sim
```

Después:

1. desbloquear y autorizar el S25 por USB;
2. abrir Pulso en el teléfono;
3. pulsar `CONECTAR GAZEBO`;
4. abrir Mission Control en
   `http://127.0.0.1:4173/?bridge=ws://127.0.0.1:9091`;
5. verificar un solo `gemma_input`, tool y action result por ciclo;
6. cerrar con `./pulso stop`.

No ejecutar `--host-brain` en esta demo. Debe existir un único cerebro.

## 5. Fallback de laboratorio

Solo si el S25 no puede actuar como cerebro:

```bash
./pulso stop
./pulso sim --host-brain
```

En este modo no conecte el agente del S25 a Gazebo. El host Ubuntu y el S25
nunca deben mandar acciones simultáneamente.

## 6. Preflight físico sin locomoción

```bash
./pulso stop
adb devices -l
./pulso real --dry-run
./pulso real
```

En la app, pulsar `CONECTAR S25`. Para cerrar el gate pendiente, sostener el
teléfono con movimiento lento, cámara expuesta, luz y textura suficientes hasta
observar `TRACKING`; conservar RGB, intrínsecos, Depth/nube, VIO/IMU, batería,
temperatura y timeline. No energizar motores Zeus.

## 7. Túnel SSH para Mission Control

Mission Control y rosbridge permanecen en loopback. Desde la laptop del
operador, sustituya `usuario@host-ubuntu` y ejecute:

```bash
ssh -NT \
  -L 4173:127.0.0.1:4173 \
  -L 9091:127.0.0.1:9091 \
  usuario@host-ubuntu
```

Mientras el túnel siga abierto, use en esa laptop:

```text
http://127.0.0.1:4173/?bridge=ws://127.0.0.1:9091
```

No cambie los servicios a `0.0.0.0` ni exponga 9091 a la red. El túnel es para
la vista del operador; el S25 conectado por USB continúa usando `adb reverse`.

## 8. Afirmación de entrega permitida

> PULSO ejecutó Gemma 4 E4B en el S25 como cerebro HIL, canonicalizó un target,
> aceptó `MOVE_TO` y el SafetyGate bloqueó el movimiento ante un obstáculo. El
> preflight físico verificó APK, modelo, cámara y bridge. ARCore `TRACKING` y la
> nube física siguen pendientes por falta de movimiento/exposición de cámara.
> Zeus no se movió y la locomoción no está validada.
