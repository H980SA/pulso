package com.pulso.app.domain

import com.pulso.app.perception.PersonDetection
import com.pulso.app.perception.PersonDetector
import com.pulso.app.sensor.PerceptionTrackObservation
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.NavigationCandidateObservation
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.security.SecureRandom
import kotlin.math.cos
import kotlin.math.sin

/** Deterministic normalization from adapter observations into cognition state. */
internal fun projectHilWorld(
    previous: WorldState,
    frame: SensorFrame,
    missionStartNs: Long,
): WorldState {
    return projectSensorWorld(previous, frame, missionStartNs)
}

/** Same normalization boundary for Gazebo HIL and the physical S25 source. */
internal fun projectSensorWorld(
    previous: WorldState,
    frame: SensorFrame,
    missionStartNs: Long,
): WorldState {
    val envelope = frame.envelope
    val navigation = frame.navigation
    val nowMs = envelope.capturedMonotonicNs / 1_000_000L
    val navigationRevision = navigation?.navigationRevision ?: previous.navigationRevision
    val firstSourceFrame = previous.source != envelope.source.name
    val candidates = navigation?.candidates.orEmpty().mapNotNull { candidate ->
        val kind = runCatching { CandidateKind.valueOf(candidate.type) }.getOrNull()
            ?: return@mapNotNull null
        Candidate(
            id = CandidateId(kind, candidate.id),
            position = Vec2(candidate.x, candidate.y),
            label = candidate.label,
            purpose = candidate.purpose,
            pathLengthM = candidate.pathLengthM,
            risk = candidate.risk,
            informationGain = candidate.informationGain,
            navigationRevision = navigationRevision,
            trackingEpoch = envelope.trackingEpoch,
            targetRevision = candidate.targetRevision,
            validUntilMonotonicMs = (
                navigation?.validUntilMonotonicNs ?: envelope.capturedMonotonicNs
                ) / 1_000_000L,
            capability = candidate.capability,
        )
    }
    val artifacts = envelope.artifactUris.map { (kind, uri) ->
        ArtifactRef(
            id = "$kind-${envelope.observationId}",
            kind = kind,
            capturedAtMonotonicMs = nowMs,
            uri = uri,
        )
    } + listOfNotNull(
        frame.metaViewJpeg?.let {
            ArtifactRef(
                id = "META-$navigationRevision",
                kind = "META_VIEW",
                capturedAtMonotonicMs = nowMs,
                uri = "ros:///pulso/navigation/metaview/compressed",
            )
        },
    )
    return previous.copy(
        worldSeq = previous.worldSeq + 1,
        sensorMapSeq = navigation?.sensorMapSeq ?: previous.sensorMapSeq,
        navigationRevision = navigationRevision,
        monotonicNowMs = nowMs,
        missionElapsedMs = (
            envelope.capturedMonotonicNs - missionStartNs
            ).coerceAtLeast(0) / 1_000_000L,
        source = envelope.source.name,
        robot = RobotState(
            pose = Pose2(
                position = Vec2(frame.robot.x, frame.robot.y),
                headingDeg = frame.robot.headingDeg,
                confidence = frame.robot.poseConfidence,
            ),
            trackingState = enumOrDefault(envelope.trackingState, TrackingState.LOST),
            trackingQuality = envelope.trackingQuality,
            trackingEpoch = envelope.trackingEpoch,
            motionState = enumOrDefault(frame.robot.motionState, MotionState.STOPPED),
            batteryFraction = frame.robot.batteryFraction,
            flashlightOn = frame.robot.flashlightOn,
            frontRangeM = frame.robot.frontRangeM,
        ),
        mission = if (firstSourceFrame) {
            Mission(
                "M-001",
                "Explorar y localizar posibles sobrevivientes",
                "Concluir la búsqueda asignada con evidencia verificable sobre sobrevivientes y cobertura alcanzable.",
            )
        } else {
            previous.mission
        },
        activeGoal = if (firstSourceFrame) {
            Goal(
                id = "G-001",
                missionId = "M-001",
                title = "Expandir cobertura sin comprometer el rover",
                successCondition =
                    "Mapear rutas transitables y priorizar evidencia humana verificable.",
            )
        } else {
            previous.activeGoal
        },
        hypotheses = if (firstSourceFrame) emptyList() else previous.hypotheses,
        targets = if (firstSourceFrame) emptyList() else previous.targets,
        candidates = candidates,
        obstacles = emptyList(),
        artifacts = artifacts,
    )
}

internal data class DetectionProjection(
    val world: WorldState,
    val decisionNeed: DecisionNeed,
    val tracks: List<PerceptionTrackObservation>,
    val signature: String,
    val semanticChanged: Boolean,
    val latencyMs: Long,
    val revision: Long,
    val navigationCandidates: List<NavigationCandidateObservation>,
)

internal fun projectDetections(
    previous: WorldState,
    previousNeed: DecisionNeed,
    frame: SensorFrame,
    detections: List<PersonDetection>,
    previousDetectionRevision: Long,
    previousSignature: String,
): DetectionProjection {
    val nowMs = frame.envelope.capturedMonotonicNs / 1_000_000L
    val ordered = detections.sortedBy { (it.leftNorm + it.rightNorm) * 0.5f }
    val signature = ordered.mapIndexed { index, detection ->
        "PERSON_${index + 1}:${(detection.confidence * 10).toInt()}:${(detection.bearingDeg / 5).toInt()}"
    }.joinToString("|")
    val semanticChanged = signature != previousSignature
    val detectionRevision = previousDetectionRevision + if (semanticChanged) 1 else 0
    val measuredRanges = ordered.map { detection -> depthRangeFor(detection, frame) }
    val targets = ordered.mapIndexed { index, detection ->
        TargetTrack(
            id = "PERSON_${index + 1}",
            label = "pose humana posible · ${detection.visibleKeypoints}/17 puntos visibles",
            bearingDeg = detection.bearingDeg,
            rangeM = measuredRanges[index],
            possibleHuman = detection.confidence,
            occlusion = null,
            revision = detectionRevision,
            observedAtMonotonicMs = nowMs,
            evidenceIds = listOf(
                "RGB-${frame.envelope.observationId}",
                "PERCEPTION-${frame.envelope.capturedMonotonicNs}",
            ),
        )
    }
    val detectorHypotheses = targets.map { target ->
        Hypothesis(
            id = "H-${target.id}",
            missionId = previous.mission.id,
            goalId = previous.activeGoal.id,
            claim =
                "${target.id} puede corresponder a una persona; todavía no confirma un sobreviviente.",
            confidence = target.possibleHuman,
            unresolved = listOf(
                "Distancia exacta y oclusión",
                "Si está atrapada o herida",
                "Consciencia o respuesta a voz",
            ),
        )
    }
    val tracks = ordered.mapIndexed { index, detection ->
        PerceptionTrackObservation(
            id = "PERSON_${index + 1}",
            label = "person",
            modelId = PersonDetector.MODEL_ID,
            confidence = detection.confidence,
            bearingDeg = detection.bearingDeg,
            leftNorm = detection.leftNorm,
            topNorm = detection.topNorm,
            rightNorm = detection.rightNorm,
            bottomNorm = detection.bottomNorm,
            revision = detectionRevision,
            inferenceLatencyMs = detection.inferenceLatencyMs,
            visibleKeypoints = detection.visibleKeypoints,
        )
    }
    val navigationCandidates = ordered.mapIndexedNotNull { index, detection ->
        val rangeM = measuredRanges[index] ?: return@mapIndexedNotNull null
        val id = "PERSON_${index + 1}"
        val absoluteBearingRad = Math.toRadians(
            (frame.robot.headingDeg + detection.bearingDeg).toDouble()
        )
        NavigationCandidateObservation(
            type = CandidateKind.TARGET.name,
            id = id,
            label = "$id · inspección humana posible",
            purpose = "Orientar cámara y solicitar evidencia visual del track medido",
            x = frame.robot.x + cos(absoluteBearingRad).toFloat() * rangeM,
            y = frame.robot.y + sin(absoluteBearingRad).toFloat() * rangeM,
            pathLengthM = rangeM,
            risk = 0f,
            informationGain = detection.confidence,
            capability = DetectionGrantIssuer.issue(id, detectionRevision, frame.envelope.trackingEpoch),
            targetRevision = detectionRevision,
        )
    }
    val detectionDomainCandidates = navigationCandidates.map { candidate ->
        Candidate(
            id = CandidateId(CandidateKind.TARGET, candidate.id),
            position = Vec2(candidate.x, candidate.y),
            label = candidate.label,
            purpose = candidate.purpose,
            pathLengthM = candidate.pathLengthM,
            risk = candidate.risk,
            informationGain = candidate.informationGain,
            navigationRevision = previous.navigationRevision,
            trackingEpoch = frame.envelope.trackingEpoch,
            targetRevision = candidate.targetRevision,
            validUntilMonotonicMs = nowMs + DETECTION_CANDIDATE_TTL_MS,
            capability = candidate.capability,
        )
    }
    val nextNeed = when {
        targets.isNotEmpty() -> DecisionNeed.INSPECT_TARGET
        previousNeed == DecisionNeed.INSPECT_TARGET -> DecisionNeed.CHOOSE_ROUTE
        else -> previousNeed
    }
    val world = previous.copy(
        worldSeq = previous.worldSeq + 1,
        semanticRevision = previous.semanticRevision + if (semanticChanged) 1 else 0,
        hypotheses = previous.hypotheses.filterNot { it.id.startsWith("H-PERSON_") } + detectorHypotheses,
        targets = targets,
        candidates = previous.candidates.filterNot {
            it.id.kind == CandidateKind.TARGET && it.id.value.startsWith("PERSON_")
        } + detectionDomainCandidates,
        artifacts = (
            previous.artifacts.filterNot { it.kind == "EGO_RGB" } +
                ArtifactRef(
                    id = "RGB-${frame.envelope.observationId}",
                    kind = "EGO_RGB",
                    capturedAtMonotonicMs = nowMs,
                    uri = "ros:///pulso/phone/rgb/compressed",
                )
            ).takeLast(32),
    )
    return DetectionProjection(
        world = world,
        decisionNeed = nextNeed,
        tracks = tracks,
        signature = signature,
        semanticChanged = semanticChanged,
        latencyMs = detections.maxOfOrNull { it.inferenceLatencyMs } ?: 0L,
        revision = detectionRevision,
        navigationCandidates = navigationCandidates,
    )
}

private fun depthRangeFor(detection: PersonDetection, frame: SensorFrame): Float? {
    val horizontalInset = (detection.rightNorm - detection.leftNorm) * 0.2f
    val verticalInset = (detection.bottomNorm - detection.topNorm) * 0.2f
    val values = frame.depthSamples.asSequence()
        .filter {
            it.uNorm in (detection.leftNorm + horizontalInset)..(detection.rightNorm - horizontalInset) &&
                it.vNorm in (detection.topNorm + verticalInset)..(detection.bottomNorm - verticalInset) &&
                it.rangeM.isFinite() && it.rangeM in 0.1f..20f
        }
        .map { it.rangeM }
        .sorted()
        .toList()
    if (values.size < MIN_DEPTH_ROI_SAMPLES) return null
    return values[values.size / 2]
}

private object DetectionGrantIssuer {
    private val secret = ByteArray(32).also(SecureRandom()::nextBytes)

    fun issue(id: String, targetRevision: Long, trackingEpoch: Long): String {
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update(secret)
        digest.update(id.toByteArray(Charsets.UTF_8))
        digest.update(ByteBuffer.allocate(16).putLong(targetRevision).putLong(trackingEpoch).array())
        return "grant_" + digest.digest().take(16).joinToString("") { "%02x".format(it) }
    }
}

private const val MIN_DEPTH_ROI_SAMPLES = 3
private const val DETECTION_CANDIDATE_TTL_MS = 15_000L

private inline fun <reified T : Enum<T>> enumOrDefault(value: String, fallback: T): T =
    runCatching { enumValueOf<T>(value.uppercase()) }.getOrDefault(fallback)
