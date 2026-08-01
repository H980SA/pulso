#!/usr/bin/env bash
set -euo pipefail

readonly PACKAGE_ID="com.pulso.app"
readonly MODEL_PATH="/storage/emulated/0/Android/data/${PACKAGE_ID}/files/models/gemma-4-E4B-it.litertlm"
readonly MODEL_SHA256="0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0"

device_count="$(adb devices | awk 'NR > 1 && $2 == "device" {count++} END {print count + 0}')"
if [[ "${device_count}" -ne 1 ]]; then
  echo "FAIL expected exactly one authorized Android device; found ${device_count}." >&2
  adb devices -l >&2
  exit 1
fi

serial="$(adb get-serialno | tr -d '\r')"
model="$(adb shell getprop ro.product.model | tr -d '\r')"
android="$(adb shell getprop ro.build.version.release | tr -d '\r')"
printf 'PASS device %s · %s · Android %s\n' "${serial}" "${model}" "${android}"

if adb shell pm path com.google.ar.core >/dev/null 2>&1; then
  echo "PASS ARCore installed"
else
  echo "FAIL ARCore missing" >&2
  exit 1
fi

if adb shell pm path "${PACKAGE_ID}" >/dev/null 2>&1; then
  echo "PASS Pulso APK installed"
else
  echo "FAIL Pulso APK missing" >&2
  exit 1
fi

device_sha256="$(adb shell sha256sum "${MODEL_PATH}" 2>/dev/null | tr -d '\r' | awk '{print $1}' || true)"
if [[ "${device_sha256}" == "${MODEL_SHA256}" ]]; then
  echo "PASS Gemma 4 E4B exact model"
else
  echo "FAIL Gemma 4 E4B missing or hash mismatch" >&2
  exit 1
fi

battery_dump="$(adb shell dumpsys battery | tr -d '\r')"
battery_level="$(awk '/level:/ {print $2; exit}' <<<"${battery_dump}")"
battery_tenths="$(awk '/temperature:/ {print $2; exit}' <<<"${battery_dump}")"
printf 'PASS battery %s%% · %d.%d°C\n' \
  "${battery_level:-?}" "$(( ${battery_tenths:-0} / 10 ))" "$(( ${battery_tenths:-0} % 10 ))"

adb reverse tcp:9091 tcp:9091
if adb reverse --list | grep -q 'tcp:9091 tcp:9091'; then
  echo "PASS adb reverse tcp:9091"
else
  echo "FAIL adb reverse tcp:9091" >&2
  exit 1
fi

camera_permission="$(adb shell dumpsys package "${PACKAGE_ID}" | awk '/android.permission.CAMERA: granted=/{print; exit}')"
audio_permission="$(adb shell dumpsys package "${PACKAGE_ID}" | awk '/android.permission.RECORD_AUDIO: granted=/{print; exit}')"
grep -q 'granted=true' <<<"${camera_permission}" && echo "PASS camera permission" || echo "WARN camera permission not granted"
grep -q 'granted=true' <<<"${audio_permission}" && echo "PASS microphone permission" || echo "WARN microphone permission not granted"

echo "SAFE: this doctor performs no Zeus motor command."
