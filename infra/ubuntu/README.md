# Estación Pulso en Ubuntu

Target reproducible: Ubuntu 22.04 amd64, ROS 2 Humble, Gazebo Fortress,
Android SDK 35, JDK 17/21, Blender y Node 20.19.4.

```bash
export PULSO_DATA_ROOT=/mnt/linux-data/pulso  # o una ruta propia escribible
./pulso install
./scripts/download_gemma4_e4b.sh "$PULSO_DATA_ROOT/models/gemma-4-E4B-it.litertlm"
./pulso doctor
```

`install` puede repetirse. No modifica `.bashrc`. Artefactos descargados,
modelos, venvs y caches quedan bajo `PULSO_DATA_ROOT`; logs/PID operativos bajo
`PULSO_STATE_ROOT` o el XDG state directory. Android deja de depender de una
ruta de usuario específica.

Las revisiones y checksums están en `versions.env`. Docker no es parte del
camino crítico y solo se instala con `PULSO_INSTALL_DOCKER=1`.

Para mañana siga exactamente
[`PULSO_IMPLEMENTATION_RUNBOOK.md`](../../documentation/PULSO_IMPLEMENTATION_RUNBOOK.md).

Fuentes primarias consultadas el 1 de agosto de 2026:

- [ROS 2 Humble en Ubuntu 22.04](https://docs.ros.org/en/humble/Releases/Release-Humble-Hawksbill.html)
- [Pareja oficial Humble + Gazebo Fortress](https://gazebosim.org/docs/fortress/ros_installation/)
- [Android command-line tools y checksums](https://developer.android.com/studio)
- [Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
