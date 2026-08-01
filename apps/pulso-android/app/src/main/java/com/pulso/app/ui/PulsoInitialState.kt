package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.Goal
import com.pulso.app.domain.Mission
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.MotionState
import com.pulso.app.domain.Pose2
import com.pulso.app.domain.RobotState
import com.pulso.app.domain.TrackingState
import com.pulso.app.domain.Vec2
import com.pulso.app.domain.WorldState

internal fun initialPulsoState(selector: ContextSelector): PulsoUiState {
    // This is an empty transport state, not demo telemetry. Production data is
    // admitted only after a frame arrives from an active sensor adapter.
    val world = WorldState(
        worldSeq = 0,
        sensorMapSeq = 0,
        navigationRevision = 0,
        semanticRevision = 0,
        monotonicNowMs = 0,
        missionElapsedMs = 0,
        source = "DISCONNECTED",
        robot = RobotState(
            pose = Pose2(Vec2(0f, 0f), 0f, 0f),
            trackingState = TrackingState.LOST,
            trackingQuality = 0f,
            trackingEpoch = 0,
            motionState = MotionState.STOPPED,
            batteryFraction = 0f,
            flashlightOn = false,
            frontRangeM = null,
        ),
        mission = Mission(
            "M-001",
            "Localizar y verificar posibles sobrevivientes",
            "Concluir la búsqueda asignada con evidencia verificable sobre sobrevivientes y cobertura alcanzable.",
        ),
        activeGoal = Goal(
            id = "G-001",
            missionId = "M-001",
            title = "Esperar una fuente sensorial verificable",
            successCondition = "Recibir el primer frame con sello temporal y origen conocido.",
        ),
        hypotheses = emptyList(),
        targets = emptyList(),
        candidates = emptyList(),
        obstacles = emptyList(),
        artifacts = emptyList(),
    )
    val cognitive = CognitiveState(
        currentQuestion = "Esperando telemetría real.",
        planSummary = "No decidir hasta recibir un WorldPacket de una fuente conectada.",
        activeSkillId = null,
        lastActionSummary = null,
    )
    val checkpoint = MissionCheckpoint(
        missionId = "M-001",
        goalId = "G-001",
        durableFindings = emptyList(),
        rejectedAlternatives = emptyList(),
        unresolved = listOf("Fuente sensorial no conectada"),
    )
    val need = DecisionNeed.CHOOSE_ROUTE
    return PulsoUiState(
        world = world,
        packet = selector.select(world, need, cognitive, checkpoint),
        cognitive = cognitive,
        checkpoint = checkpoint,
        decisionNeed = need,
    )
}
