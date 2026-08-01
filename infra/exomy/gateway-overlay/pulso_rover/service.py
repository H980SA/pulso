"""Gateway policy overlay: leases, revisions and conservative supervised ground pulses."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import ClassVar
from uuid import UUID

from pulso_rover.adapters.base import RobotAdapter
from pulso_rover.config import Settings
from pulso_rover.contracts import (
    Availability,
    CapabilitiesResponse,
    Capability,
    CommandRecord,
    CommandRequest,
    CommandStatus,
    CommandType,
    ControlLease,
    ControlLeaseRequest,
    ControlMode,
    OperatingStage,
    SafetyState,
    SpeedProfileName,
    WorldState,
    utc_now,
)
from pulso_rover.errors import DomainError
from pulso_rover.motion import SPEED_PROFILES, map_motion
from pulso_rover.probes import SystemProbe
from pulso_rover.store import AuditStore


class RoverGatewayService:
    unavailable_sensors: ClassVar[tuple[str, ...]] = (
        "actual_velocity",
        "wheel_feedback",
        "robot_battery",
        "imu",
        "odometry",
        "pose",
        "obstacle_detection",
        "distance_travelled",
        "microphone",
        "light",
    )

    def __init__(self, settings: Settings, adapter: RobotAdapter, store: AuditStore, probe: SystemProbe) -> None:
        self.settings = settings
        self.adapter = adapter
        self.store = store
        self.probe = probe
        self.revision = 0
        self.mode = ControlMode.SHADOW if settings.stage == "SHADOW" else ControlMode.DISARMED
        self.estop_latched = False
        self.active_lease: ControlLease | None = None
        self.active_command_id: UUID | None = None
        self.commanded_motion = "ZERO"

    def capabilities(self) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            capabilities=[
                Capability(name="camera", availability=Availability.AVAILABLE, accuracy="UNCALIBRATED", detail="Fixed 640x480 camera configured at 10 FPS"),
                Capability(name="drive_timed", availability=Availability.AVAILABLE, accuracy="OPEN_LOOP", detail="Six drive motors; PWM command only, no encoder feedback"),
                Capability(name="turn_timed", availability=Availability.AVAILABLE, accuracy="OPEN_LOOP", detail="Point-turn command; angle is not measured"),
                Capability(name="crab_timed", availability=Availability.AVAILABLE, accuracy="OPEN_LOOP", detail="Six steerable wheels; displacement is not measured"),
                Capability(name="rotate_degrees", availability=Availability.UNAVAILABLE, accuracy=None, detail="Requires a validated session calibration or IMU"),
                Capability(name="navigate", availability=Availability.UNAVAILABLE, accuracy=None, detail="Requires odometry, pose and obstacle detection"),
            ],
            speed_profiles=SPEED_PROFILES,
            max_duration_ms=self.settings.max_duration_ms,
        )

    def _lease_is_valid(self, lease_id: object) -> bool:
        return bool(
            self.active_lease
            and self.active_lease.lease_id == lease_id
            and self.active_lease.expires_at > utc_now()
        )

    def acquire_lease(self, request: ControlLeaseRequest) -> ControlLease:
        if self.estop_latched:
            raise DomainError("ESTOP_LATCHED", "Reset e-stop before acquiring control", 409)
        if self.active_lease and self.active_lease.expires_at > utc_now():
            raise DomainError("LEASE_CONFLICT", "A controller already holds the lease", 409)
        ttl = min(request.ttl_seconds, self.settings.max_lease_seconds)
        lease = ControlLease(holder=request.holder, expires_at=utc_now() + timedelta(seconds=ttl))
        self.active_lease = lease
        if self.settings.allow_actuation:
            self.mode = ControlMode.ARMED
        self.revision += 1
        self.store.append_event("LEASE_ACQUIRED", lease.model_dump_json())
        return lease

    def release_lease(self, lease_id: object) -> None:
        if not self._lease_is_valid(lease_id):
            raise DomainError("INVALID_LEASE", "Lease is missing, stale or expired", 409)
        self.active_lease = None
        self.mode = ControlMode.SHADOW if self.settings.stage == "SHADOW" else ControlMode.DISARMED
        self.revision += 1
        self.store.append_event("LEASE_RELEASED", json.dumps({"lease_id": str(lease_id)}))

    async def world_state(self) -> WorldState:
        if self.active_lease and self.active_lease.expires_at <= utc_now():
            self.active_lease = None
            self.mode = ControlMode.SHADOW if self.settings.stage == "SHADOW" else ControlMode.DISARMED
            self.revision += 1
        ros, camera, system = await self.probe.collect()
        return WorldState(
            world_revision=self.revision,
            stage=OperatingStage(self.settings.stage),
            control_mode=self.mode,
            active_lease=self.active_lease,
            active_command_id=self.active_command_id,
            ros=ros,
            camera=camera,
            system=system,
            safety=SafetyState(
                estop_latched=self.estop_latched,
                max_speed_percent=max(SPEED_PROFILES.values()),
                max_duration_ms=self.settings.max_duration_ms,
                heartbeat_timeout_ms=self.settings.heartbeat_timeout_ms,
                allow_actuation=self.settings.allow_actuation,
            ),
            commanded_motion=self.commanded_motion,
            unavailable=list(self.unavailable_sensors),
        )

    @staticmethod
    def _digest(request: CommandRequest) -> str:
        canonical = json.dumps(request.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _validate_motion_admission(self, request: CommandRequest) -> None:
        if self.settings.stage not in {"WHEELS_UP", "GROUND"} or self.mode != ControlMode.ARMED:
            raise DomainError("ACTUATION_NOT_ARMED", "Physical motion requires an armed field-stage control lease", 409)
        if self.active_lease is None or request.requested_by != self.active_lease.holder:
            raise DomainError("LEASE_HOLDER_MISMATCH", "requested_by must match the active lease holder", 409)
        if self.settings.stage == "GROUND":
            if not self.settings.ground_supervised_confirmed:
                raise DomainError("GROUND_NOT_CONFIRMED", "Supervised ground gate is not confirmed", 409)
            if request.speed_profile != SpeedProfileName.CREEP:
                raise DomainError("GROUND_SPEED_LIMIT", "GROUND accepts only the CREEP profile", 409)
            if request.duration_ms is None or request.duration_ms > 150:
                raise DomainError("GROUND_DURATION_LIMIT", "GROUND pulses must be 1-150 ms", 409)

    async def submit_command(self, request: CommandRequest, idempotency_key: str) -> CommandRecord:
        if not idempotency_key or len(idempotency_key) > 200:
            raise DomainError("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key is required and <=200 chars")
        digest = self._digest(request)
        existing = self.store.find_by_idempotency_key(idempotency_key)
        if existing:
            if existing.request_digest != digest:
                raise DomainError("IDEMPOTENCY_CONFLICT", "The same key was used with a different command", 409)
            return existing
        if request.expected_world_revision != self.revision:
            raise DomainError("STALE_WORLD_STATE", f"Expected revision {request.expected_world_revision}; current is {self.revision}", 409)
        if self.estop_latched and request.command_type != CommandType.STOP:
            raise DomainError("ESTOP_LATCHED", "Only stop is accepted while e-stop is latched", 409)
        if request.command_type not in {CommandType.STOP, CommandType.PARK} and not self._lease_is_valid(request.lease_id):
            raise DomainError("INVALID_LEASE", "Motion requires a valid control lease", 409)
        if request.duration_ms and request.duration_ms > self.settings.max_duration_ms:
            raise DomainError("DURATION_LIMIT", "Command duration exceeds safety limit")

        is_motion = request.command_type not in {CommandType.STOP, CommandType.PARK}
        if is_motion and self.settings.allow_actuation:
            self._validate_motion_admission(request)
            ros, _camera, system = await self.probe.collect()
            if ros.bridge != Availability.AVAILABLE:
                raise DomainError("ROS_UNAVAILABLE", "ROSBridge is unavailable", 503)
            if system.undervoltage_active is not False:
                raise DomainError("POWER_UNSAFE", "Active or unknown undervoltage blocks physical motion", 409)

        candidate = map_motion(request)
        record = CommandRecord(
            idempotency_key=idempotency_key,
            request_digest=digest,
            request=request,
            status=CommandStatus.VALIDATED,
            candidate=candidate,
        )
        self.store.save_command(record)
        self.active_command_id = record.command_id
        self.commanded_motion = "ZERO" if request.command_type in {CommandType.STOP, CommandType.PARK} else "NONZERO"
        self.revision += 1
        try:
            result = await self.adapter.execute(request)
            record.candidate = result.candidate
            record.dispatched_to_ros = result.dispatched
            record.detail = result.detail
            record.status = CommandStatus.SUCCEEDED if result.dispatched else CommandStatus.SHADOWED
        except Exception as exc:
            await self.adapter.stop()
            record.status = CommandStatus.FAULT
            record.detail = f"Adapter failure: {type(exc).__name__}"
            self.mode = ControlMode.FAULTED
            raise DomainError("ADAPTER_FAILURE", record.detail, 503) from exc
        finally:
            record.completed_at = utc_now()
            self.commanded_motion = "ZERO"
            self.active_command_id = None
            self.revision += 1
            self.store.save_command(record)
            self.store.append_event("COMMAND_COMPLETED", record.model_dump_json())
        return record

    async def engage_estop(self, reason: str) -> None:
        self.estop_latched = True
        self.mode = ControlMode.ESTOP_LATCHED
        self.active_lease = None
        self.commanded_motion = "ZERO"
        self.revision += 1
        await self.adapter.stop()
        self.store.append_event("ESTOP_ENGAGED", json.dumps({"reason": reason}))

    def reset_estop(self, reason: str) -> None:
        if not self.estop_latched:
            raise DomainError("ESTOP_NOT_LATCHED", "E-stop is not currently latched", 409)
        self.estop_latched = False
        self.mode = ControlMode.SHADOW if self.settings.stage == "SHADOW" else ControlMode.DISARMED
        self.revision += 1
        self.store.append_event("ESTOP_RESET", json.dumps({"reason": reason}))
