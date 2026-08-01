export function parsePhoneTelemetry(payload) {
  const value = asPayload(payload);
  if (!isObject(value) || value.contract_version !== "pulso.phone-telemetry.v1") return null;
  const imu = isObject(value.imu) ? value.imu : {};
  const battery = isObject(value.battery) ? value.battery : {};
  return {
    kind: "phone-telemetry",
    contractVersion: value.contract_version,
    capturedNs: asFinite(value.captured_monotonic_ns),
    source: asString(value.source),
    frameId: asString(value.frame_id),
    imuCapturedNs: asFinite(imu.captured_monotonic_ns),
    accelerationMps2: vector3(imu.acceleration_mps2),
    angularVelocityRadps: vector3(imu.angular_velocity_radps),
    batteryFraction: asFinite(battery.fraction),
    batteryTemperatureC: asFinite(battery.temperature_c),
  };
}

export function parseCameraInfo(payload) {
  const value = asPayload(payload);
  if (!isObject(value)) return null;
  if (value.contract_version !== "pulso.phone-camera-info.v1") {
    return parseRosCameraInfo(value);
  }
  const k = finiteArray(value.k, 9);
  if (!k || k.length !== 9) return null;
  return {
    kind: "phone-camera-info",
    contractVersion: value.contract_version,
    capturedNs: asFinite(value.captured_monotonic_ns),
    frameId: asString(value.frame_id),
    calibrationSource: asString(value.calibration_source),
    width: asFinite(value.width),
    height: asFinite(value.height),
    model: asString(value.model),
    distortionModel: asString(value.distortion_model),
    k,
  };
}

function parseRosCameraInfo(value) {
  const k = finiteArray(value.k, 9);
  const width = asFinite(value.width);
  const height = asFinite(value.height);
  if (!k || k.length !== 9 || width === null || height === null) return null;
  const stamp = isObject(value.header?.stamp) ? value.header.stamp : {};
  const seconds = asFinite(stamp.sec);
  const nanoseconds = asFinite(stamp.nanosec);
  return {
    kind: "phone-camera-info",
    contractVersion: "sensor_msgs/msg/CameraInfo",
    capturedNs: seconds === null || nanoseconds === null ? null : seconds * 1_000_000_000 + nanoseconds,
    frameId: asString(value.header?.frame_id),
    calibrationSource: "ros/camera_info",
    width,
    height,
    model: "pinhole",
    distortionModel: asString(value.distortion_model),
    k,
  };
}

function vector3(value) {
  const result = finiteArray(value, 3);
  return result?.length === 3 ? result : null;
}

function finiteArray(value, minimum) {
  if (!Array.isArray(value) || value.length < minimum) return null;
  const result = value.map(asFinite);
  return result.every((item) => item !== null) ? result : null;
}

function asPayload(value) {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  }
  return isObject(value) ? value : null;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function asString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asFinite(value) {
  const number = typeof value === "string" && value.trim() ? Number(value) : value;
  return Number.isFinite(number) ? number : null;
}
