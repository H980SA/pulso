package com.pulso.app.robot

import com.pulso.app.sensor.real.RealPose2d
import com.pulso.app.sensor.real.bearingDeg
import com.pulso.app.sensor.real.normalizeDegrees
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlin.math.sin

sealed interface ZeusCommand {
    data class Drive(val travelAngleDeg: Float, val power: Int, val headingCorrectionDeg: Float) : ZeusCommand
    data object Stop : ZeusCommand
}

/** Interoperable SunFounder Controller region payload; no firmware source is embedded. */
object ZeusWireProtocol {
    fun encode(command: ZeusCommand): String {
        val regions = MutableList(REGION_COUNT) { "0" }
        when (command) {
            ZeusCommand.Stop -> {
                regions[STOP_BUTTON_REGION] = "1"
                regions[MOVE_JOYSTICK_REGION] = "0,0"
                regions[HEADING_JOYSTICK_REGION] = "0,0"
            }
            is ZeusCommand.Drive -> {
                val boundedPower = command.power.coerceIn(0, MAX_WIRE_POWER)
                regions[MOVE_JOYSTICK_REGION] = joystick(command.travelAngleDeg, boundedPower)
                val correction = command.headingCorrectionDeg.coerceIn(-MAX_HEADING_CORRECTION_DEG, MAX_HEADING_CORRECTION_DEG)
                regions[HEADING_JOYSTICK_REGION] = if (kotlin.math.abs(correction) < 1f) "0,0" else joystick(correction, HEADING_RADIUS)
            }
        }
        return regions.joinToString(";")
    }

    private fun joystick(angleDeg: Float, radius: Int): String {
        val radians = Math.toRadians(angleDeg.toDouble())
        val x = (sin(radians) * radius).roundToInt()
        val y = (cos(radians) * radius).roundToInt()
        return "$x,$y"
    }

    const val MAX_WIRE_POWER = 28
    private const val MAX_HEADING_CORRECTION_DEG = 45f
    private const val HEADING_RADIUS = 100
    private const val REGION_COUNT = 26
    private const val STOP_BUTTON_REGION = 5
    private const val MOVE_JOYSTICK_REGION = 10
    private const val HEADING_JOYSTICK_REGION = 16
}

data class ClosedLoopEvidence(val pose: RealPose2d, val frontRangeM: Float?)

data class ClosedLoopTarget(val x: Float, val y: Float, val lookOnly: Boolean)

data class PlannedZeusCommand(val command: ZeusCommand, val terminalStatus: String? = null)

/** Pure bounded policy: each result is valid for one short control tick and must be refreshed. */
class ZeusClosedLoopPlanner {
    fun plan(target: ClosedLoopTarget, evidence: ClosedLoopEvidence, nowNs: Long): PlannedZeusCommand {
        if (nowNs - evidence.pose.capturedMonotonicNs !in 0..MAX_EVIDENCE_AGE_NS) {
            return PlannedZeusCommand(ZeusCommand.Stop, "STALE_VIO")
        }
        val distance = hypot(target.x - evidence.pose.x, target.y - evidence.pose.y)
        if (distance > MAX_TARGET_DISTANCE_M) return PlannedZeusCommand(ZeusCommand.Stop, "TARGET_OUT_OF_BOUNDS")
        val desiredHeading = bearingDeg(evidence.pose.x, evidence.pose.y, target.x, target.y)
        val headingError = normalizeDegrees(desiredHeading - evidence.pose.headingDeg)
        if (target.lookOnly) {
            if (kotlin.math.abs(headingError) <= LOOK_COMPLETE_DEG) return PlannedZeusCommand(ZeusCommand.Stop, "REACHED")
            return PlannedZeusCommand(
                ZeusCommand.Drive(0f, 0, headingError.coerceIn(-MAX_TURN_DEG, MAX_TURN_DEG)),
            )
        }
        if (distance <= MOVE_COMPLETE_M) return PlannedZeusCommand(ZeusCommand.Stop, "REACHED")
        val range = evidence.frontRangeM ?: return PlannedZeusCommand(ZeusCommand.Stop, "NO_CURRENT_FRONT_RANGE")
        if (range <= MIN_CLEARANCE_M) return PlannedZeusCommand(ZeusCommand.Stop, "FRONT_BLOCKED")
        if (kotlin.math.abs(headingError) > DRIVE_HEADING_LIMIT_DEG) {
            return PlannedZeusCommand(
                ZeusCommand.Drive(0f, 0, headingError.coerceIn(-MAX_TURN_DEG, MAX_TURN_DEG)),
            )
        }
        val speed = (MIN_POWER + distance * POWER_PER_METER).roundToInt().coerceIn(MIN_POWER, MAX_POWER)
        return PlannedZeusCommand(ZeusCommand.Drive(0f, speed, headingError))
    }

    companion object {
        const val MAX_EVIDENCE_AGE_NS = 500_000_000L
        const val MAX_TARGET_DISTANCE_M = 3f
        const val MIN_CLEARANCE_M = 0.48f
        const val MAX_POWER = 24
        private const val MIN_POWER = 12
        private const val POWER_PER_METER = 5f
        private const val MAX_TURN_DEG = 35f
        private const val DRIVE_HEADING_LIMIT_DEG = 18f
        private const val LOOK_COMPLETE_DEG = 6f
        private const val MOVE_COMPLETE_M = 0.22f
    }
}
