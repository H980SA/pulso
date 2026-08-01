# PULSO — verificación y recuperación

Verifique de abajo hacia arriba. No atribuya a Gemma un fallo de sensor, bridge,
geometría o safety.

## 1. Gate local de entrega

```bash
scripts/tests/pulso_delivery_test.sh
```

Comprueba sintaxis, ejecutables, contrato CLI, rutas portables, pins, límite
Zeus, higiene Git/LFS y APK local cuando está provisionado.

Pruebas de componentes:

```bash
cd apps/pulso-mission-control && npm test
cd ../pulso-brain-host
../../.tools/venvs/litert-lm-py313/bin/python -m unittest discover -s tests -v
cd ../pulso-android
./gradlew --no-daemon testDebugUnitTest assembleDebug
```

Los tests Android incluyen reglas del source físico, geometría local, audio,
torch/Zeus y ViewModel. No ejecutan ARCore, sensores ni E4B sobre el S25.

Conteo final observado:

| Suite | Resultado |
| --- | --- |
| Android | 69 tests; `assembleDebug` y lint correctos |
| Mission Control | 26 tests JS + 6 tests Python |
| Brain host | 32 tests |
| E2E | 9 tests |

## 2. Estación Ubuntu

```bash
./pulso install
./pulso doctor
```

No avance con `FAIL`. Docker y NVIDIA solo son opcionales cuando el camino
seleccionado no los necesita.

## 3. Simulación

```bash
./pulso sim
```

Este comando espera el S25 como único cerebro. En la app pulse `CONECTAR
GAZEBO`. `./pulso sim --host-brain` es un fallback de laboratorio y nunca debe
coexistir con el agente S25.

Orden de diagnóstico:

1. proceso, temperatura y `/clock`;
2. nodos/TF;
3. RGB, depth, VIO, IMU y sonar;
4. `/map`, candidatos y MetaView;
5. bridge local;
6. input/tool/result de Gemma;
7. Mission Control.

Tests HIL locales:

```bash
node scripts/hil_smoke_test.mjs ws://127.0.0.1:9091
node scripts/hil_stop_test.mjs ws://127.0.0.1:9091
node scripts/hil_security_test.mjs ws://127.0.0.1:9091
node scripts/hil_bootstrap_frontier_test.mjs ws://127.0.0.1:9091
```

El security test debe probar que ground truth y motor safe no atraviesan el
bridge. La ruta REAL es todavía más estrecha: solo publishers de telemetría,
sin services/actions y sin `/pulso/hil/action_intent`.

## 4. S25 preflight

```bash
adb devices -l
./pulso real --dry-run
./pulso real
```

Debe existir exactamente un Samsung S25 autorizado. La CLI comprueba:

- APK E4B fijado;
- modelo host y modelo copiado al teléfono;
- permisos CAMERA/RECORD_AUDIO;
- túnel ADB local;
- Activity arrancable.

Eso no valida `ANDROID_REAL`; solo prepara su ejecución.

## 5. Gate runtime `ANDROID_REAL`

Estado actual: **implementado y parcialmente comprobado en S25**. APK, modelo,
cámara y bridge fueron verificados. La prueba no produjo ARCore `TRACKING` ni
nube porque el teléfono permaneció inmóvil y la cámara no estuvo expuesta.

Una corrida aceptable conserva:

| Control | Evidencia |
| --- | --- |
| ARCore | install/resume y tracking state |
| RGB | JPEG físico fresco e intrínsecos |
| Depth | DEPTH16 actual o ausencia explícita, nunca sintética |
| VIO/IMU | pose, epoch, acelerómetro y gyro con timestamps |
| MetaView | mapa/candidatos derivados de depth real |
| Gemma | modelo/hash, warm, input, tool, result y latencia |
| Torch | callback Camera2 confirmado |
| TTS/audio | callback TTS y métricas/hash PCM sin guardar audio |
| Térmica | temperatura, battery y transición de thermal guard |
| Zeus | dry-run; cero frames de locomoción enviados |

Atlas confirma la promoción solo después de revisar esa evidencia.

## 6. Estados y recuperación del source

| Estado/fallo | Recuperación |
| --- | --- |
| `ARCORE_INSTALL_REQUESTED` | completar instalación, volver y pulsar `CONECTAR S25` |
| permission denied | conceder permiso y reiniciar la Activity |
| tracking paused/stopped | mejorar luz/textura, mover despacio, reintentar |
| no current depth | esperar frame; no convertir ausencia en rango libre |
| torch unconfirmed | dejar estado desconocido; no afirmar encendido |
| heartbeat stale | autonomía se pausa y se intenta STOP |
| thermal stop | cerrar misión, enfriar bajo threshold y revalidar |
| bridge offline | cerebro local continúa; recuperar solo telemetría |

## 7. Zeus

El cliente default `dryRun=true` no transmite comandos a motores. STOP puede
quedar queued, pero no existe ACK stock. Estados válidos incluyen
`STOP_ATTEMPTED_UNCONFIRMED`, `DISARMED_STOP_UNCONFIRMED` y
`TTL_STOP_UNCONFIRMED`.

La locomoción solo puede evaluarse en otro gate con:

- dead-man MCU verificado;
- E-stop físico y persona junto al paro;
- operator presence explícita;
- costmap/trayectoria físicos validados;
- prueba de caída Wi-Fi/app y corte de corriente.

## 8. Mission Control

Abra `http://127.0.0.1:4173/?bridge=ws://127.0.0.1:9091`.

`WAITING` es el estado correcto si falta un tópico. No existe un modo sintético
para esconder la ausencia. Revise consola, bridge y producer antes de recargar.

## 9. Logs y cierre

```bash
./pulso stop
```

Logs/PIDs:

```text
${PULSO_STATE_ROOT:-$HOME/.local/state/pulso}/orchestrator/
```

Si la parada supera diez segundos, conserve PID/log y diagnostique. No mate un
PID no validado ni lance un segundo Gazebo: dos `/clock` corrompen TF.

## 10. Matriz de afirmaciones

| Afirmación | Estado permitido |
| --- | --- |
| E4B funciona en simulación estricta | sí, evidencia preservada |
| `ANDROID_REAL` existe en código | sí |
| E4B decide en HIL desde el S25 | sí; GPU warm 11.385 s y ciclo total 56.937 s, incluida espera de acción |
| ID de target propuesto se canonicaliza con seguridad | sí; `MOVE_TO` aceptado y SafetyGate bloqueó por obstáculo |
| APK/modelo/cámara/bridge funcionan en preflight físico | sí |
| ARCore `TRACKING`, nube y sensores físicos E2E funcionan | no; faltó movimiento/exposición de cámara |
| E4B tiene latencia/termal sostenida aceptable en S25 | no medido |
| Zeus valida acciones en dry-run | sí |
| STOP Zeus está confirmado | no, protocolo sin ACK |
| locomoción Zeus está validada | no |

El procedimiento reproducible de entrega está en
[`evidence/FINAL_VALIDATION.md`](evidence/FINAL_VALIDATION.md).
