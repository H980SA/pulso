"""Pure deterministic safety policy, shared by tests and the ROS node."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MotionCommand:
    linear_x: float
    angular_z: float


@dataclass(frozen=True)
class SafetyDecision:
    command: MotionCommand
    state: str
    reason: str


@dataclass(frozen=True)
class SafetyPolicy:
    stop_distance_m: float = 0.18
    slow_distance_m: float = 0.45
    command_timeout_s: float = 0.35
    max_linear_mps: float = 0.32
    max_angular_rad_s: float = 1.6
    sensor_timeout_s: float = 0.75

    def evaluate(
        self,
        command: MotionCommand,
        command_age_s: float,
        front_range_m: float | None,
        bumper_pressed: bool,
        estop: bool,
        range_age_s: float = 0.0,
        bumper_age_s: float = 0.0,
    ) -> SafetyDecision:
        stopped = MotionCommand(0.0, 0.0)
        if estop:
            return SafetyDecision(stopped, "STOPPED", "ESTOP")
        if bumper_pressed:
            return SafetyDecision(stopped, "STOPPED", "BUMPER")
        if command_age_s > self.command_timeout_s:
            return SafetyDecision(stopped, "STOPPED", "COMMAND_WATCHDOG")

        linear = max(-self.max_linear_mps, min(self.max_linear_mps, command.linear_x))
        angular = max(-self.max_angular_rad_s, min(self.max_angular_rad_s, command.angular_z))
        if linear > 0.0 and bumper_age_s > self.sensor_timeout_s:
            return SafetyDecision(stopped, "STOPPED", "BUMPER_WATCHDOG")
        if linear > 0.0 and (
            range_age_s > self.sensor_timeout_s
            or front_range_m is None
            or not math.isfinite(front_range_m)
        ):
            return SafetyDecision(stopped, "STOPPED", "RANGE_WATCHDOG")
        if linear > 0.0:
            if front_range_m <= self.stop_distance_m:
                return SafetyDecision(stopped, "STOPPED", "NEAR_FIELD_OBSTACLE")
            if front_range_m < self.slow_distance_m:
                scale = (front_range_m - self.stop_distance_m) / (
                    self.slow_distance_m - self.stop_distance_m
                )
                return SafetyDecision(
                    MotionCommand(linear * max(0.0, min(1.0, scale)), angular),
                    "LIMITED",
                    "NEAR_FIELD_SLOWDOWN",
                )
        return SafetyDecision(MotionCommand(linear, angular), "CLEAR", "NONE")
