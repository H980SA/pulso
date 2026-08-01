package com.pulso.app.domain

internal data class MissionFocusProjection(
    val world: WorldState,
    val checkpoint: MissionCheckpoint,
    val cognitive: CognitiveState,
)

/** Persist a model-selected focus in the compact mission memory. */
internal fun reduceMissionFocus(
    world: WorldState,
    checkpoint: MissionCheckpoint,
    cognitive: CognitiveState,
    title: String,
    successCondition: String,
    reason: String,
): MissionFocusProjection {
    require(title.isNotBlank() && successCondition.isNotBlank() && reason.isNotBlank())
    val nextSemanticRevision = world.semanticRevision + 1
    val goal = Goal(
        id = "G-${nextSemanticRevision.toString().padStart(4, '0')}",
        missionId = world.mission.id,
        title = title.trim(),
        successCondition = successCondition.trim(),
    )
    return MissionFocusProjection(
        world = world.copy(
            worldSeq = world.worldSeq + 1,
            semanticRevision = nextSemanticRevision,
            activeGoal = goal,
            hypotheses = world.hypotheses.filter { it.goalId == goal.id },
        ),
        checkpoint = checkpoint.copy(
            missionId = world.mission.id,
            goalId = goal.id,
            durableFindings = (
                checkpoint.durableFindings + "Focus: ${goal.title}. Reason: ${reason.trim()}"
                ).takeLast(8),
            unresolved = listOf("Success condition: ${goal.successCondition}"),
        ),
        cognitive = cognitive.copy(
            currentQuestion = "¿Qué evidencia permite completar ${goal.id}: ${goal.successCondition}?",
            planSummary = reason.trim(),
            lastActionSummary = "Mission focus changed to ${goal.id}.",
        ),
    )
}
