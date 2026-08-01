package com.pulso.app.robot

import android.os.SystemClock
import com.pulso.app.audio.PhoneAudioActuator
import com.pulso.app.sensor.NavigationCandidateObservation
import com.pulso.app.sensor.real.AndroidRealSource
import com.pulso.app.sensor.real.RealPose2d
import com.pulso.app.tools.ActionIntent
import com.pulso.app.tools.ActionKind
import com.pulso.app.tools.ActionResult
import com.pulso.app.tools.PulsoActionSink
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.withTimeout

/** Integrates typed Pulso actions without weakening the independent Zeus arming boundary. */
class AndroidRealActionSink(
    private val source: AndroidRealSource,
    private val rover: RoverMotorClient,
    private val torch: PhoneTorchActuator,
    private val audio: PhoneAudioActuator,
) : PulsoActionSink, AutoCloseable {
    private val motionMutex = Mutex()
    private val planner = ZeusClosedLoopPlanner()

    suspend fun connectRover(): ActionResult = rover.connect()

    /** Must be called from an explicit operator action; tool dispatch never arms the rover. */
    suspend fun armRover(operatorPresent: Boolean = false): ActionResult = rover.arm(operatorPresent)

    suspend fun disarmRover(reason: String = "OPERATOR_DISARM"): ActionResult = rover.disarm(reason)

    override suspend fun dispatch(intent: ActionIntent): ActionResult {
        if (source.isThermallyPaused() && intent.kind != ActionKind.STOP) {
            val turningTorchOff = intent.kind == ActionKind.SET_FLASHLIGHT && intent.parameters["enabled"] == false
            if (!turningTorchOff) {
                return ActionResult(false, "THERMAL_STOP", "Phone thermal guard paused physical actions.")
            }
        }
        return when (intent.kind) {
        ActionKind.STOP -> rover.command(ZeusCommand.Stop)
        ActionKind.SET_FLASHLIGHT -> {
            val enabled = intent.parameters["enabled"] as? Boolean
                ?: return ActionResult(false, "INVALID_ARGUMENT", "enabled must be Boolean.")
            torch.setEnabled(enabled)
        }
        ActionKind.SPEAK -> {
            val text = intent.parameters["text"] as? String
                ?: return ActionResult(false, "INVALID_ARGUMENT", "text is required.")
            audio.speak(text)
        }
        ActionKind.LISTEN -> {
            val duration = (intent.parameters["duration_seconds"] as? Number)?.toInt()
                ?: return ActionResult(false, "INVALID_ARGUMENT", "duration_seconds is required.")
            audio.listen(duration)
        }
        ActionKind.REQUEST_VIEW -> requestView(intent)
        ActionKind.MOVE_TO -> runMotion(intent, lookOnly = false)
        ActionKind.LOOK_AT -> runMotion(intent, lookOnly = true)
            else -> ActionResult(false, "UNSUPPORTED_ON_PHONE", "${intent.kind} is not owned by the physical actuator adapter.")
        }
    }

    private suspend fun requestView(intent: ActionIntent): ActionResult {
        val target = resolveTarget(intent) ?: return staleTarget()
        if (!candidateTypeAllows(target, ActionKind.REQUEST_VIEW)) {
            return ActionResult(false, "TARGET_TYPE_MISMATCH", "${target.type}:${target.id} cannot authorize a requested view.")
        }
        val requestedKind = intent.parameters["view_kind"] as? String ?: "CANDIDATE_VIEW"
        val baseline = source.latestFrameCaptureNs()
        val frame = runCatching {
            withTimeout(VIEW_TIMEOUT_MS) {
                source.observations.first { candidate ->
                    candidate.envelope.capturedMonotonicNs > baseline && when (requestedKind) {
                        "TARGET_VIEW", "CANDIDATE_VIEW", "EGO_RGB" -> candidate.egoRgbJpeg != null
                        else -> candidate.metaViewJpeg != null
                    }
                }
            }
        }.getOrElse {
            return ActionResult(false, "VIEW_CAPTURE_TIMEOUT", "No fresh measured $requestedKind arrived after the request.")
        }
        val revalidated = source.latestNavigation()?.let {
            authorizeCurrentCandidate(intent, it, SystemClock.elapsedRealtimeNanos())
        } ?: return staleTarget()
        if (!candidateTypeAllows(revalidated, ActionKind.REQUEST_VIEW)) {
            return ActionResult(false, "TARGET_TYPE_MISMATCH", "${revalidated.type}:${revalidated.id} cannot authorize a requested view.")
        }
        val capturedNs = frame.envelope.capturedMonotonicNs
        val scene = source.metaViewSceneJson(capturedNs)
            ?: return ActionResult(false, "VIEW_CAPTURE_MISMATCH", "No MetaView scene exists for the authorized capture timestamp.")
        val actionId = "REAL-VIEW-${System.nanoTime()}"
        return ActionResult(
            accepted = true,
            status = "CAPTURED",
            detail = "Returned the latest measured pulso.metaview-scene.v1 scene for ${target.id}.",
            data = mapOf(
                "action_id" to actionId,
                "artifact_capture_ns" to capturedNs,
                "view_kind" to requestedKind,
                "contract_version" to "pulso.metaview-scene.v1",
                "scene_json" to scene,
            ),
        )
    }

    private suspend fun runMotion(intent: ActionIntent, lookOnly: Boolean): ActionResult = motionMutex.withLock {
        val candidate = resolveTarget(intent) ?: return@withLock staleTarget()
        if (!candidateTypeAllows(candidate, intent.kind)) {
            return@withLock ActionResult(
                false,
                "TARGET_TYPE_MISMATCH",
                "${candidate.type}:${candidate.id} does not permit ${intent.kind}.",
            )
        }
        val initialNavigation = source.latestNavigation()
            ?: return@withLock ActionResult(false, "NO_NAVIGATION", "No current measured local navigation scene exists.")
        if (SystemClock.elapsedRealtimeNanos() > initialNavigation.validUntilMonotonicNs) {
            return@withLock ActionResult(false, "STALE_NAVIGATION", "The measured navigation scene expired.")
        }
        var lastTimestamp = -1L
        val result = withTimeoutOrNull(if (lookOnly) LOOK_TIMEOUT_MS else MOVE_TIMEOUT_MS) {
            while (true) {
                val frame = source.observations.first { it.envelope.capturedMonotonicNs > lastTimestamp }
                lastTimestamp = frame.envelope.capturedMonotonicNs
                if (intent.expectedTrackingEpoch != null && frame.envelope.trackingEpoch != intent.expectedTrackingEpoch) {
                    rover.command(ZeusCommand.Stop)
                    return@withTimeoutOrNull ActionResult(false, "TRACKING_EPOCH_CHANGED", "VIO relocalized during the action.")
                }
                val currentCandidate = source.latestNavigation()?.let {
                    authorizeCurrentCandidate(intent, it, SystemClock.elapsedRealtimeNanos())
                }
                if (currentCandidate == null || !candidateTypeAllows(currentCandidate, intent.kind)) {
                    rover.command(ZeusCommand.Stop)
                    return@withTimeoutOrNull staleTarget()
                }
                val pose = RealPose2d(
                    frame.robot.x,
                    frame.robot.y,
                    frame.robot.headingDeg,
                    frame.envelope.capturedMonotonicNs,
                )
                val planned = planner.plan(
                    ClosedLoopTarget(currentCandidate.x, currentCandidate.y, lookOnly),
                    ClosedLoopEvidence(pose, frame.robot.frontRangeM),
                    SystemClock.elapsedRealtimeNanos(),
                )
                if (rover.dryRun && planned.terminalStatus != null) {
                    return@withTimeoutOrNull if (planned.terminalStatus == "REACHED") {
                        ActionResult(true, "DRY_RUN_REACHED", "VIO target is already within the completion bound; no motor frame was sent.")
                    } else {
                        ActionResult(false, planned.terminalStatus, "Dry-run safety policy rejected the bounded command.")
                    }
                }
                val commandResult = rover.command(planned.command)
                if (!commandResult.accepted) return@withTimeoutOrNull commandResult
                planned.terminalStatus?.let { terminal ->
                    return@withTimeoutOrNull when (terminal) {
                        "REACHED" -> ActionResult(true, "COMPLETED", "Closed-loop VIO target reached.", rover.safetyStatus())
                        else -> ActionResult(false, terminal, "Closed-loop safety policy stopped motion.", rover.safetyStatus())
                    }
                }
                if (rover.dryRun) {
                    return@withTimeoutOrNull ActionResult(
                        true,
                        "DRY_RUN",
                        "One closed-loop command was evaluated from current VIO/range and no motor frame was sent.",
                        rover.safetyStatus(),
                    )
                }
                return@withTimeoutOrNull ActionResult(
                    true,
                    "PULSE_COMPLETED",
                    "One supervised CREEP pulse completed. A fresh Depth/VIO frame is required before another pulse.",
                    rover.safetyStatus(),
                )
            }
            error("Closed-loop exited unexpectedly")
        }
        rover.command(ZeusCommand.Stop)
        result ?: ActionResult(false, "MOTION_TIMEOUT", "Bounded physical action timed out and STOP was issued.", rover.safetyStatus())
    }

    private fun resolveTarget(intent: ActionIntent): NavigationCandidateObservation? {
        val navigation = source.latestNavigation() ?: return null
        return authorizeCurrentCandidate(intent, navigation, SystemClock.elapsedRealtimeNanos())
    }

    private fun staleTarget() = ActionResult(false, "STALE_OR_UNKNOWN_TARGET", "Target is not present in the current measured scene.")

    override fun close() {
        rover.close()
        torch.close()
        audio.close()
    }

    private companion object {
        const val LOOK_TIMEOUT_MS = 12_000L
        const val MOVE_TIMEOUT_MS = 25_000L
        const val VIEW_TIMEOUT_MS = 2_500L
    }
}

/** Fail-closed authorization against the latest measured scene, kept pure for contract tests. */
internal fun authorizeCurrentCandidate(
    intent: ActionIntent,
    navigation: com.pulso.app.sensor.NavigationObservation,
    nowMonotonicNs: Long,
): NavigationCandidateObservation? {
    val target = intent.target ?: return null
    if (nowMonotonicNs > navigation.validUntilMonotonicNs) return null
    val current = navigation.candidates.firstOrNull { it.type == target.kind.name && it.id == target.value }
        ?: return null
    val presentedGrant = intent.candidateCapability ?: return null
    if (presentedGrant != current.capability) return null
    if (current.capability.length < MIN_OPAQUE_GRANT_LENGTH) return null
    if (intent.expectedTargetRevision != null && intent.expectedTargetRevision != current.targetRevision) return null
    // A spatial ID still present in this fresh DEPTH16-derived scene is geometrically revalidated.
    return current
}

internal fun candidateTypeAllows(candidate: NavigationCandidateObservation, action: ActionKind): Boolean = when (action) {
    ActionKind.MOVE_TO -> candidate.type == "FRONTIER"
    ActionKind.LOOK_AT -> candidate.type in setOf("VIEWPOINT", "TARGET")
    ActionKind.REQUEST_VIEW -> candidate.type in setOf("FRONTIER", "VIEWPOINT", "TARGET")
    else -> false
}

private const val MIN_OPAQUE_GRANT_LENGTH = 16
