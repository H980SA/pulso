package com.pulso.app.domain

data class Vec2(val x: Float, val y: Float)

data class Pose2(
    val position: Vec2,
    val headingDeg: Float,
    val confidence: Float,
)

enum class TrackingState { TRACKING, LIMITED, LOST }

enum class MotionState { STOPPED, MOVING, BLOCKED, FAULT }

data class RobotState(
    val pose: Pose2,
    val trackingState: TrackingState,
    val trackingQuality: Float,
    val trackingEpoch: Long,
    val motionState: MotionState,
    val batteryFraction: Float,
    val flashlightOn: Boolean,
    val frontRangeM: Float?,
)

enum class CandidateKind { VIEWPOINT, FRONTIER, TARGET, ANCHOR }

data class CandidateId(val kind: CandidateKind, val value: String)

data class Candidate(
    val id: CandidateId,
    val position: Vec2,
    val label: String,
    val purpose: String,
    val pathLengthM: Float,
    val risk: Float,
    val informationGain: Float,
    val navigationRevision: Long,
    val trackingEpoch: Long,
    val targetRevision: Long? = null,
    val validUntilMonotonicMs: Long,
    val capability: String = "",
)

data class TargetTrack(
    val id: String,
    val label: String,
    val bearingDeg: Float,
    val rangeM: Float?,
    val possibleHuman: Float,
    val occlusion: Float?,
    val revision: Long,
    val observedAtMonotonicMs: Long,
    val evidenceIds: List<String>,
)

data class Mission(
    val id: String,
    val title: String,
    val successCondition: String = "Complete the declared mission with current, verifiable evidence.",
)

data class Goal(
    val id: String,
    val missionId: String,
    val title: String,
    val successCondition: String,
)

data class Hypothesis(
    val id: String,
    val missionId: String,
    val goalId: String?,
    val claim: String,
    val confidence: Float,
    val unresolved: List<String>,
)

data class ArtifactRef(
    val id: String,
    val kind: String,
    val capturedAtMonotonicMs: Long,
    val uri: String,
)

data class AcousticObservation(
    val id: String,
    val label: String,
    val confidence: Float,
    val durationMs: Long,
    val rmsDbfs: Float,
    val marginAboveNoiseDb: Float,
    val bearingKnown: Boolean,
    val observedAtMonotonicMs: Long,
    val validUntilMonotonicMs: Long,
)

data class WorldState(
    val worldSeq: Long,
    val sensorMapSeq: Long,
    val navigationRevision: Long,
    val semanticRevision: Long,
    val monotonicNowMs: Long,
    val missionElapsedMs: Long,
    val source: String,
    val robot: RobotState,
    val mission: Mission,
    val activeGoal: Goal,
    val hypotheses: List<Hypothesis>,
    val targets: List<TargetTrack>,
    val candidates: List<Candidate>,
    val obstacles: List<List<Vec2>>,
    val artifacts: List<ArtifactRef>,
    val acousticObservations: List<AcousticObservation> = emptyList(),
)
