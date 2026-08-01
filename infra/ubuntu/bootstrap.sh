#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/versions.env"

readonly DATA_ROOT="${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/pulso}"
readonly STATE_ROOT="${PULSO_STATE_ROOT:-${XDG_STATE_HOME:-${HOME}/.local/state}/pulso}"
readonly ANDROID_SDK="${PULSO_ANDROID_SDK_ROOT:-${DATA_ROOT}/android-sdk}"
readonly DOWNLOADS="${DATA_ROOT}/cache/downloads"

die() { printf 'ERROR %s\n' "$*" >&2; exit 1; }

[[ -r /etc/os-release ]] || die "No se puede identificar el sistema operativo."
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID}" == "ubuntu" && "${VERSION_CODENAME:-}" == "jammy" ]] || \
  die "Se requiere Ubuntu 22.04 Jammy; se encontró ${PRETTY_NAME}."
[[ "$(dpkg --print-architecture)" == "amd64" ]] || \
  die "Este bootstrap reproducible está fijado para Ubuntu 22.04 amd64."
(( EUID != 0 )) || die "Ejecute ./pulso install como usuario normal con acceso a sudo, no como root."
command -v sudo >/dev/null 2>&1 || die "sudo no está instalado."
sudo -v || die "Se requiere autorización sudo para instalar dependencias del sistema."

if ! mkdir -p "${DATA_ROOT}" "${STATE_ROOT}" 2>/dev/null; then
  die "${DATA_ROOT} no es escribible. Monte el disco o defina PULSO_DATA_ROOT."
fi
[[ -w "${DATA_ROOT}" && -w "${STATE_ROOT}" ]] || \
  die "Los directorios de datos/estado no son escribibles."

mkdir -p \
  "${DATA_ROOT}/models" "${DATA_ROOT}/bags" "${DATA_ROOT}/logs" \
  "${DATA_ROOT}/vendor" "${DATA_ROOT}/tools" "${DATA_ROOT}/venvs" \
  "${DATA_ROOT}/cache/gradle" \
  "${DATA_ROOT}/cache/pip" "${DATA_ROOT}/cache/gazebo/fuel" "${DOWNLOADS}"

apt_install() {
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
}

verified_download() {
  local url="$1" destination="$2" expected="$3"
  if [[ -f "${destination}" ]] && printf '%s  %s\n' "${expected}" "${destination}" \
      | sha256sum --check --status; then
    return
  fi
  curl --fail --location --retry 5 --retry-all-errors \
    --output "${destination}.part" "${url}"
  printf '%s  %s\n' "${expected}" "${destination}.part" | sha256sum --check -
  mv -f "${destination}.part" "${destination}"
}

sudo apt-get update
apt_install \
  ca-certificates curl gnupg lsb-release locales software-properties-common
sudo add-apt-repository universe -y
sudo apt-get update
apt_install \
  jq git git-lfs rsync tmux unzip zip xz-utils build-essential cmake ninja-build \
  pkg-config ffmpeg mesa-utils python3-pip python3-venv python3-opencv \
  openjdk-17-jdk openjdk-21-jdk blender netcat-openbsd \
  android-sdk-platform-tools-common
sudo locale-gen en_US en_US.UTF-8

readonly INSTALL_USER="${SUDO_USER:-${USER}}"
sudo groupadd --force plugdev
if ! id -nG "${INSTALL_USER}" | tr ' ' '\n' | grep -Fxq plugdev; then
  sudo usermod -aG plugdev "${INSTALL_USER}"
  printf 'AVISO se añadió %s a plugdev; cierre sesión antes de usar ADB por USB.\n' "${INSTALL_USER}"
fi
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb

export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="${JAVA_HOME}/bin:${PATH}"

ros_deb="ros2-apt-source_${PULSO_ROS_APT_SOURCE_VERSION}.jammy_all.deb"
verified_download \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${PULSO_ROS_APT_SOURCE_VERSION}/${ros_deb}" \
  "${DOWNLOADS}/${ros_deb}" "${PULSO_ROS_APT_SOURCE_SHA256}"
if ! dpkg-query -W -f='${Version}' ros2-apt-source 2>/dev/null \
    | grep -Fq "${PULSO_ROS_APT_SOURCE_VERSION}"; then
  sudo dpkg -i "${DOWNLOADS}/${ros_deb}"
fi

sudo apt-get update
apt_install \
  ros-humble-desktop ros-humble-ros-gz \
  ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-slam-toolbox \
  ros-humble-robot-localization ros-humble-depth-image-proc \
  ros-humble-image-transport-plugins ros-humble-pointcloud-to-laserscan \
  ros-humble-cv-bridge ros-humble-vision-opencv ros-humble-rqt-image-view \
  ros-humble-teleop-twist-keyboard ros-humble-xacro \
  ros-humble-joint-state-publisher ros-humble-joint-state-publisher-gui \
  ros-humble-robot-state-publisher ros-humble-rosbridge-server \
  python3-colcon-common-extensions python3-rosdep python3-vcstool

android_zip="commandlinetools-linux-${PULSO_ANDROID_TOOLS_REVISION}_latest.zip"
verified_download \
  "https://dl.google.com/android/repository/${android_zip}" \
  "${DOWNLOADS}/${android_zip}" "${PULSO_ANDROID_TOOLS_SHA256}"
if [[ ! -x "${ANDROID_SDK}/cmdline-tools/latest/bin/sdkmanager" ]]; then
  android_stage="$(mktemp -d)"
  trap 'rm -rf "${android_stage:-}"' EXIT
  unzip -q "${DOWNLOADS}/${android_zip}" -d "${android_stage}"
  mkdir -p "${ANDROID_SDK}/cmdline-tools"
  rm -rf "${ANDROID_SDK}/cmdline-tools/latest"
  mv "${android_stage}/cmdline-tools" "${ANDROID_SDK}/cmdline-tools/latest"
  rm -rf "${android_stage}"
  trap - EXIT
fi
export ANDROID_HOME="${ANDROID_SDK}"
export ANDROID_SDK_ROOT="${ANDROID_SDK}"
export PATH="${ANDROID_SDK}/cmdline-tools/latest/bin:${ANDROID_SDK}/platform-tools:${PATH}"
set +o pipefail
yes | sdkmanager --licenses >/dev/null
license_status="${PIPESTATUS[1]}"
set -o pipefail
[[ "${license_status}" == "0" ]] || die "No se pudieron aceptar las licencias Android."
sdkmanager \
  "platform-tools" \
  "platforms;android-${PULSO_ANDROID_PLATFORM}" \
  "build-tools;${PULSO_ANDROID_BUILD_TOOLS}"

node_archive="node-v${PULSO_NODE_VERSION}-linux-x64.tar.xz"
verified_download "https://nodejs.org/dist/v${PULSO_NODE_VERSION}/${node_archive}" \
  "${DOWNLOADS}/${node_archive}" "${PULSO_NODE_LINUX_X64_SHA256}"
node_dir="${DATA_ROOT}/tools/node-v${PULSO_NODE_VERSION}-linux-x64"
if [[ ! -x "${node_dir}/bin/node" ]]; then
  tar -xJf "${DOWNLOADS}/${node_archive}" -C "${DATA_ROOT}/tools"
fi
ln -sfn "$(basename "${node_dir}")" "${DATA_ROOT}/tools/node-current"

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  sudo rosdep init
fi
rosdep update
set +u
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
set -u
rosdep install --from-paths "${PROJECT_ROOT}/sim/ros2_ws/src" --ignore-src -r -y
git lfs install --skip-repo
if git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "${PROJECT_ROOT}" lfs pull
fi
yolo_model="${PROJECT_ROOT}/apps/pulso-android/app/src/main/assets/models/yolo11n_pose.onnx"
[[ -f "${yolo_model}" ]] || die "Modelo YOLO LFS ausente: ${yolo_model}"
yolo_sha="$(sha256sum "${yolo_model}" | awk '{print $1}')"
yolo_bytes="$(wc -c < "${yolo_model}" | tr -d ' ')"
[[ "${yolo_sha}" == "${PULSO_YOLO_SHA256}" && "${yolo_bytes}" == "${PULSO_YOLO_BYTES}" ]] || \
  die "Modelo YOLO no materializado o distinto; revise git lfs pull."

if [[ "${PULSO_INSTALL_DOCKER:-0}" == "1" ]]; then
  apt_install docker.io
  sudo systemctl enable --now docker
fi

# Install project Python runtimes unless explicitly skipped for a lightweight host.
if [[ "${PULSO_SKIP_AI_RUNTIMES:-0}" != "1" ]]; then
  PULSO_DATA_ROOT="${DATA_ROOT}" PULSO_ANDROID_SDK_ROOT="${ANDROID_SDK}" \
    "${PROJECT_ROOT}/scripts/install_brain_runtime.sh"
  PULSO_DATA_ROOT="${DATA_ROOT}" PULSO_ANDROID_SDK_ROOT="${ANDROID_SDK}" \
    "${PROJECT_ROOT}/scripts/install_perception_runtime.sh"
fi

if [[ "${PULSO_SKIP_MODEL_DOWNLOAD:-0}" != "1" ]]; then
  "${PROJECT_ROOT}/scripts/download_gemma4_e4b.sh" \
    "${DATA_ROOT}/models/${PULSO_GEMMA_FILENAME}"
fi

if [[ "${PULSO_SKIP_ANDROID_BUILD:-0}" != "1" ]]; then
  apk_path="${PROJECT_ROOT}/dist/${PULSO_APK_FILENAME}"
  PULSO_DATA_ROOT="${DATA_ROOT}" ANDROID_HOME="${ANDROID_SDK}" \
    ANDROID_SDK_ROOT="${ANDROID_SDK}" \
    "${PROJECT_ROOT}/scripts/android/build_debug.sh" \
    "ws://127.0.0.1:9091" "${apk_path}"
  mkdir -p "${STATE_ROOT}"
  apk_sha="$(sha256sum "${apk_path}" | awk '{print $1}')"
  apk_bytes="$(wc -c < "${apk_path}" | tr -d ' ')"
  {
    printf 'export PULSO_LOCAL_APK_SHA256=%q\n' "${apk_sha}"
    printf 'export PULSO_LOCAL_APK_BYTES=%q\n' "${apk_bytes}"
  } > "${STATE_ROOT}/artifacts.env"
fi

printf '\nPulso instalado con LFS, Gemma E4B y APK loopback. Verifique con:\n  source %s/infra/ubuntu/pulso-env.sh\n  %s/pulso doctor\n' \
  "${PROJECT_ROOT}" "${PROJECT_ROOT}"
