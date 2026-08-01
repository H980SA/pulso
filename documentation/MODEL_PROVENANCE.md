# Pulso model provenance and measured evidence

Status date: 2026-08-01. Hashes identify exact measured files. Native and
simulation validation are separate from phone runtime/sensor validation.

## Gemma 4 E4B — target mission brain

E4B is the current product decision and is now verified in the native profile
and strict simulation E2E. It has not inherited any E2B measurement.

| Property | Verified value/status |
| --- | --- |
| Product role | Target local multimodal mission brain |
| Upstream/revision | `litert-community/gemma-4-E4B-it-litert-lm` at `f7ad3343bd6ebc9607f4dc3bc4f2398bd5749bc5` |
| File | `gemma-4-E4B-it.litertlm` |
| Ubuntu path | `${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/pulso}/models/gemma-4-E4B-it.litertlm` |
| Size | 3,659,530,240 bytes |
| SHA-256 | `0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0` |
| Native profile | `sim/logs/e2e/gemma4-e4b-native-profile.json`: GPU warm 11,666 ms; inference 1,518 ms; expected `move_to(FRONTIER:F_SAFE)` passed |
| Strict simulation E2E | `sim/logs/e2e/e4b-final-20260801T071618Z/e2e-report.json`: `result.ok=true`, zero failures, read-only and no mocks |
| Historical Android APK audit | Earlier HIL artifact `dist/pulso-debug.apk`: 225,086,438 bytes; SHA-256 `f8444bfa287c48a9b7c6f5fd4cf01460b6c75dea867f2f61cb7062528564f293`; it predates `ANDROID_REAL` and is not the current delivery pin. |
| Current Android APK identity | 225609468 bytes; SHA-256 `949bae5458233e4b675b01c1b0d46ba2bc797442d0fa772a42cc0fddd59e19b0`; `pulso real` rejects a mismatch. |
| S25 HIL E4B | GPU warm 11.385 s; real brain cycle 56.937 s total including action wait; target ID safely canonicalized, `MOVE_TO` accepted, SafetyGate blocked on obstacle |
| S25 physical preflight | APK, model, camera and bridge verified; ARCore `TRACKING` and real point cloud pending because the phone was stationary and its camera was not exposed |

The native profile itself has SHA-256
`01022e564674650153ad893fcc136a300bc79a24fbc0bc212e5dc44f8ed29558`;
the strict report has SHA-256
`05bc9aa48b0af02f0c2087a62f52d96b91306f4c577fdc6f0668d70b4f3311de`.
The profile is a bounded single prompt, so 11,666/1,518 ms are not sustained
p50/p95. That earlier report proves the host-controlled simulation chain; the
later S25 HIL capture is the Android inference evidence. Neither proves physical
sensors or motors.

The historical APK hash records that earlier audit only. Any Android rebuild
changes the artifact and requires updating `dist/pulso-debug.apk` and its size/hash
in `infra/ubuntu/versions.env` together before install.
The later S25 capture supersedes the earlier disconnected-device caveat for
artifact identity and HIL cognition. It does not close the physical sensor
gate: there is still no ARCore `TRACKING` or real point cloud evidence.

## Gemma 4 E2B — earlier harness baseline

E2B is no longer the target brain. The following data is retained because it
proves the multimodal/tool/navigation harness worked with one real model and
provides a regression baseline. It does **not** validate E4B.

| Property | Value |
| --- | --- |
| Upstream | `litert-community/gemma-4-E2B-it-litert-lm` |
| File | `gemma-4-E2B-it.litertlm` |
| Size | 2,588,147,712 bytes (2.59 GB as displayed by Hugging Face) |
| SHA-256 | `181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c` |
| Runtime | LiteRT-LM 0.13.1 through native Python 3.13 host, or Google ADK Kotlin 0.6.0 on Android |
| Input used | Selective text `WorldPacket` and demand-only JPEG visual views |
| Storage | Historical Mac audit under `.tools/models/`; portable Ubuntu data root; copied outside the APK to the S25 |

The audited `scripts/android/download_model.sh` now reproduces the current E4B
artifact, resumes interrupted transfers and rejects a hash mismatch. The E2B
identity above remains only as a historical ledger entry.

The [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)
identifies Gemma 4 as a multimodal family and lists Apache 2.0. Model use and
redistribution must also follow the current notices linked by Google and the
upstream repository. Pulso does not redistribute the weights inside its APK.

### Smoke nativo preservado

El ledger
[`native-model-smoke-2026-07-31.json`](../apps/pulso-brain-host/evidence/native-model-smoke-2026-07-31.json)
registra una ejecución con el archivo y hash anteriores, `litert-lm-api 0.13.1`,
Python 3.13 y backend GPU:

| Medida | Resultado observado |
| --- | ---: |
| Engine warm | 2392 ms |
| MetaView 800×800 → tool call estructurado | 1699 ms |
| Tool result → respuesta pública | 115 ms |
| Contexto después del follow-up | 1353 tokens |

La entrada visual tenía 136,524 bytes y SHA-256
`1cf14cd8b980a1709fbcaa4015ea0908f20dbd7d3df02ae52ea2ee298190409c`.
Gemma emitió `stop {}` y después respondió `Stop.`. El resultado de STOP fue
inyectado por el harness para probar el protocolo; **no** fue un resultado de
navegación ni un movimiento físico. Estas cifras prueban carga, multimodalidad y
frontera de tool calling en ese Mac; no son p50/p95 sostenidos, latencia S25 ni
evidencia E4B.

La validación final del mismo host en Ubuntu/RTX 3050 observó un engine GPU warm
en 3225 ms. El cierre ordenado dejó `exit_code=0` y `signal=0` en el registro
del supervisor después de aplicar el workaround Linux que omite únicamente la
segunda finalización global de OpenCL/LiteRT, una vez cerrado el engine. Esto
prueba carga y lifecycle del baseline E2B en Linux; tampoco es p50/p95 de
inferencia ni evidencia E4B.

## YOLO11n-pose ONNX — saliency sensor

| Property | Value |
| --- | --- |
| Upstream | `Ultralytics/YOLO11`, `yolo11n-pose.pt` |
| Packaged file | `app/src/main/assets/models/yolo11n_pose.onnx` |
| SHA-256 | `898538c90094a92a1aeb5ed0bdb96c55c7837991fcc1d120991b74218fd2644a` |
| Graph | ONNX opset 17, static input `[1,3,640,640]`, output `[1,56,8400]` |
| Ubuntu runtime | ONNX Runtime GPU 1.23.2, `CUDAExecutionProvider`, intra/inter-op = 1 |
| Android runtime | ONNX Runtime Android 1.27.0, CPU, four intra-op threads |
| Policy | score ≥ 0.18, IoU NMS 0.45, at most four pose clues |

The detector is not the survivor classifier. It is allowed to say only that a
human-shaped pose may deserve attention. Gemma must inspect fresh RGB evidence
before forming a hypothesis about a person, injury, entrapment, or
consciousness; a missed detection is not evidence of absence.

The [official YOLO11 model card](https://huggingface.co/Ultralytics/YOLO11)
lists the pose model and AGPL-3.0 licensing, with a separate enterprise option.
That is acceptable for this open hackathon prototype; a closed commercial
distribution must comply with AGPL or replace/license this component.
[ONNX Runtime's mobile guide](https://onnxruntime.ai/docs/tutorials/mobile/)
documents the Android package and recommends measuring latency, binary size,
memory, and power on the target device.

## Reproducible detector benchmark

Command on Ubuntu:

```bash
source "${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/pulso}/venvs/perception-qa/bin/activate"
python sim/tools/evaluate_person_detector.py \
  --model apps/pulso-android/app/src/main/assets/models/yolo11n_pose.onnx \
  --threshold 0.18 --runs 3 \
  art/current/ragdoll/navigable/renders/pulso_navigable_A.png \
  art/current/ragdoll/navigable/renders/pulso_navigable_B.png \
  sim/logs/qa/sim_phone_frame.png
```

Observed on the Ryzen 7 5700G CPU after one warm-up run:

| Image | Pose clues | Best score | Visible keypoints | Median inference |
| --- | ---: | ---: | ---: | ---: |
| Accepted survivor A render | 1 | 0.7857 | 12/17 | 83.08 ms |
| Accepted survivor B render | 1 | 0.2417 | 0/17 | 101.16 ms |
| Empty forward simulator frame | 0 | — | — | 101.23 ms |

These numbers prove graph decoding and scene coverage on the workstation. They
are not S25 latency claims. The S25 test must record cold load, warm p50/p95,
thermal state, battery draw, false negatives across route viewpoints, and
Gemma/vision contention while both models remain resident.

At the later final capture, `adb devices -l` enumerated the S25 and the physical
preflight verified the delivery APK, E4B model, camera and bridge. E4B also ran
the real HIL decision described above. Because the phone remained stationary
and the camera was not exposed to the scene, ARCore `TRACKING`, the real point
cloud, sustained thermal behavior and physical sensor quality remain unproven.

The portable operational sequence is `./pulso install`, `./pulso doctor`,
`./pulso sim`, then `./pulso stop` before `./pulso real --dry-run`. An external
`PULSO_DATA_ROOT` is optional; changing storage location does not create phone
runtime evidence. Only Atlas may promote the S25 sensor/cognition path after a
preserved supervised session. Zeus locomotion remains unvalidated.

## Rejected detector baseline

EfficientDet Lite0 and Lite2 were tested at thresholds down to 0.10 and returned
no person for either accepted prone/occluded survivor render. YOLO11n generic
detection found A only weakly and missed B. YOLO11n-pose was selected because it
covered both accepted cases while producing no clue on the empty simulator
frame. The rejected EfficientDet asset was removed; it is not packaged in the
APK.
