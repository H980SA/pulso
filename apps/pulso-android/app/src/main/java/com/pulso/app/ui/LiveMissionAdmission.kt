package com.pulso.app.ui

import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.WorldState

internal data class LiveMissionAdmission(
    val cognitive: CognitiveState,
    val checkpoint: MissionCheckpoint,
    val decisionNeed: DecisionNeed,
)

/** Replaces disconnected placeholders exactly once, when the first measured frame is admitted. */
internal fun admitFirstLiveMission(previous: PulsoUiState, world: WorldState): LiveMissionAdmission {
    if (previous.hasLiveObservation) {
        return LiveMissionAdmission(previous.cognitive, previous.checkpoint, previous.decisionNeed)
    }
    val goal = world.activeGoal
    return LiveMissionAdmission(
        cognitive = previous.cognitive.copy(
            currentQuestion = "¿Qué ruta observable avanza «${goal.title}» con menor riesgo?",
            planSummary = "Comparar candidatos FRONTIER/VIEWPOINT vigentes y elegir una acción segura.",
        ),
        checkpoint = previous.checkpoint.copy(
            missionId = world.mission.id,
            goalId = goal.id,
            unresolved = listOf("Elegir una ruta vigente con evidencia sensorial."),
        ),
        decisionNeed = DecisionNeed.CHOOSE_ROUTE,
    )
}
