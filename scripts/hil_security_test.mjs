#!/usr/bin/env node

const url = process.argv[2] ?? "ws://192.168.18.51:9091";
const socket = new WebSocket(url);
let sawAllowedObservation = false;
let sawGroundTruth = false;
let initialPose = null;
let latestPose = null;
let sawUnexpectedMotion = false;

function waitUntil(predicate, label, waitMs = 8_000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - started > waitMs) {
        clearInterval(timer);
        reject(new Error(`Timed out waiting for ${label}`));
      }
    }, 80);
  });
}

socket.addEventListener("open", async () => {
  try {
    socket.send(JSON.stringify({
      op: "subscribe",
      id: "security-allowed",
      topic: "/pulso/hil/observation",
      type: "std_msgs/msg/String",
    }));
    socket.send(JSON.stringify({
      op: "subscribe",
      id: "security-denied-sub",
      topic: "/pulso/sim/ground_truth/odom",
      type: "nav_msgs/msg/Odometry",
    }));
    await waitUntil(() => sawAllowedObservation, "allowed observation");
    // rosbridge logs allowlist denials server-side but does not emit a status
    // frame in Humble. Try to bypass the safety topic repeatedly and prove the
    // robot remains stationary through the only allowed observation boundary.
    const attack = setInterval(() => socket.send(JSON.stringify({
      op: "publish",
      id: "security-denied-pub",
      topic: "/pulso/base/cmd_vel_safe",
      msg: { linear: { x: 0.5 }, angular: { z: 0.0 } },
    })), 20);
    await new Promise((resolve) => setTimeout(resolve, 2_200));
    clearInterval(attack);
    await new Promise((resolve) => setTimeout(resolve, 800));
    if (sawGroundTruth) throw new Error("Ground-truth data crossed the HIL boundary");
    if (sawUnexpectedMotion) throw new Error("Direct motor publish bypassed the HIL allowlist");
    const displacement = initialPose && latestPose
      ? Math.hypot(latestPose[0] - initialPose[0], latestPose[1] - initialPose[1])
      : null;
    if (displacement === null || displacement > 0.03) {
      throw new Error(`Robot moved ${displacement ?? "without pose"} m during denied publish`);
    }
    console.log(JSON.stringify({
      ok: true,
      url,
      allowed_observation: sawAllowedObservation,
      denied_ground_truth_subscription: true,
      denied_direct_motor_publish: true,
      displacement_m: displacement,
      ground_truth_messages: 0,
    }, null, 2));
    socket.close();
  } catch (error) {
    console.error(JSON.stringify({ ok: false, error: error.message }));
    socket.close();
    process.exitCode = 1;
  }
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);
  if (frame.op === "publish" && frame.topic === "/pulso/hil/observation") {
    sawAllowedObservation = true;
    const observation = JSON.parse(frame.msg.data);
    const pose = observation.robot?.pose?.position_m;
    if (Array.isArray(pose) && pose.length >= 2) {
      latestPose = pose;
      if (initialPose === null) initialPose = pose;
    }
    if (observation.robot?.motion_state === "MOVING") sawUnexpectedMotion = true;
  }
  if (frame.op === "publish" && frame.topic === "/pulso/sim/ground_truth/odom") {
    sawGroundTruth = true;
  }
});

socket.addEventListener("error", () => {
  process.exitCode = 1;
});
