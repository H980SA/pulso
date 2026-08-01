package com.pulso.app.demo

import com.pulso.app.domain.ArtifactRef
import com.pulso.app.domain.Candidate
import com.pulso.app.domain.CandidateId
import com.pulso.app.domain.CandidateKind
import com.pulso.app.domain.Goal
import com.pulso.app.domain.Hypothesis
import com.pulso.app.domain.Mission
import com.pulso.app.domain.MotionState
import com.pulso.app.domain.Pose2
import com.pulso.app.domain.RobotState
import com.pulso.app.domain.TargetTrack
import com.pulso.app.domain.TrackingState
import com.pulso.app.domain.Vec2
import com.pulso.app.domain.WorldState

fun demoWorld(nowMs: Long = 1_043_000L): WorldState {
    val navigationRevision = 27L
    val trackingEpoch = 3L
    return WorldState(
        worldSeq = 319,
        sensorMapSeq = 9_814,
        navigationRevision = navigationRevision,
        semanticRevision = 51,
        monotonicNowMs = nowMs,
        missionElapsedMs = 17 * 60_000L + 26_420L,
        source = "REPLAY",
        robot = RobotState(
            pose = Pose2(Vec2(3.06f, -0.52f), 180f, 0.87f),
            trackingState = TrackingState.TRACKING,
            trackingQuality = 0.91f,
            trackingEpoch = trackingEpoch,
            motionState = MotionState.STOPPED,
            batteryFraction = 0.73f,
            flashlightOn = false,
            frontRangeM = 1.42f,
        ),
        mission = Mission("M-001", "Localizar y verificar posibles sobrevivientes"),
        activeGoal = Goal(
            id = "G-007",
            missionId = "M-001",
            title = "Confirmar o descartar C03",
            successCondition = "Obtener dos señales independientes o declarar que no puede verificarse desde posiciones seguras.",
        ),
        hypotheses = listOf(
            Hypothesis(
                id = "H-012",
                missionId = "M-001",
                goalId = "G-007",
                claim = "C03 podría ser una persona atrapada.",
                confidence = 0.64f,
                unresolved = listOf("No se observa el rostro", "No se confirma movimiento"),
            )
        ),
        targets = listOf(
            TargetTrack(
                id = "C03",
                label = "forma parcialmente humana",
                bearingDeg = 31f,
                rangeM = 2.4f,
                possibleHuman = 0.76f,
                occlusion = 0.68f,
                revision = 8,
                observedAtMonotonicMs = nowMs - 2_119,
                evidenceIds = listOf("frame_821", "target_C03_821", "depth_C03_821"),
            ),
            TargetTrack(
                id = "C07",
                label = "posible prenda azul",
                bearingDeg = -38f,
                rangeM = 5.1f,
                possibleHuman = 0.47f,
                occlusion = 0.42f,
                revision = 3,
                observedAtMonotonicMs = nowMs - 8_400,
                evidenceIds = listOf("frame_806"),
            ),
        ),
        candidates = listOf(
            Candidate(
                CandidateId(CandidateKind.VIEWPOINT, "VP-17"),
                Vec2(-1.55f, -0.35f),
                "A · ángulo al rostro",
                "Reducir oclusión de C03",
                4.9f,
                0.18f,
                0.91f,
                navigationRevision,
                trackingEpoch,
                validUntilMonotonicMs = nowMs + 12_000,
                capability = "demo_grant_vp17_123456789",
            ),
            Candidate(
                CandidateId(CandidateKind.VIEWPOINT, "VP-18"),
                Vec2(-0.85f, 0.65f),
                "B · vista elevada lateral",
                "Separar torso de escombros",
                4.3f,
                0.26f,
                0.83f,
                navigationRevision,
                trackingEpoch,
                validUntilMonotonicMs = nowMs + 12_000,
                capability = "demo_grant_vp18_123456789",
            ),
            Candidate(
                CandidateId(CandidateKind.FRONTIER, "FR-021"),
                Vec2(6.35f, -1.9f),
                "C · corredor desconocido",
                "Explorar habitación B",
                3.8f,
                0.31f,
                0.72f,
                navigationRevision,
                trackingEpoch,
                validUntilMonotonicMs = nowMs + 20_000,
                capability = "demo_grant_fr021_12345678",
            ),
            Candidate(
                CandidateId(CandidateKind.TARGET, "C03"),
                Vec2(-2.75f, -1.2f),
                "C03 · track actual",
                "Centrar candidato humano",
                5.9f,
                0.36f,
                0.78f,
                navigationRevision,
                trackingEpoch,
                targetRevision = 8,
                validUntilMonotonicMs = nowMs + 5_000,
                capability = "demo_grant_target_c03_12345",
            ),
        ),
        obstacles = listOf(
            rectangle(-3.8f, -2.8f, -2.0f, 2.8f),
            rectangle(-0.3f, 0.15f, -2.8f, -0.55f),
            rectangle(-0.3f, 0.15f, 0.45f, 2.8f),
            rectangle(3.55f, 4.15f, -2.8f, -0.85f),
            rectangle(3.55f, 4.15f, 0.2f, 2.8f),
            rectangle(7.2f, 7.75f, -0.8f, 2.8f),
            rectangle(4.9f, 5.8f, -2.7f, -2.15f),
        ),
        artifacts = listOf(
            ArtifactRef("metaview_NAV27", "META_VIEW", nowMs - 180, "memory://metaview_NAV27"),
            ArtifactRef("candidate_VS17", "CANDIDATE_VIEW", nowMs - 150, "memory://candidate_VS17"),
            ArtifactRef("frame_914", "EGO_RGB", nowMs - 200, "memory://frame_914"),
        ),
    )
}

private fun rectangle(left: Float, right: Float, bottom: Float, top: Float) = listOf(
    Vec2(left, bottom),
    Vec2(right, bottom),
    Vec2(right, top),
    Vec2(left, top),
)
