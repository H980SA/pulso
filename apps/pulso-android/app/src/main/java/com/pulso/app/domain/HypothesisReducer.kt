package com.pulso.app.domain

internal data class HypothesisProjection(
    val world: WorldState,
    val checkpoint: MissionCheckpoint,
    val cognitive: CognitiveState,
    val hypothesis: Hypothesis,
    val evidenceRefs: List<String>,
)

/** Keeps Gemma's explicit hypotheses attached to the active mission and goal. */
internal fun reduceHypothesis(
    world: WorldState,
    checkpoint: MissionCheckpoint,
    cognitive: CognitiveState,
    requestedId: String,
    claim: String,
    confidence: Float,
    unresolved: List<String>,
    evidenceRefs: List<String>,
): HypothesisProjection {
    require(requestedId.isNotBlank() && claim.isNotBlank())
    require(confidence in 0f..1f)
    val nextSemanticRevision = world.semanticRevision + 1
    val id = requestedId.takeUnless { it.equals("NEW", ignoreCase = true) }
        ?: "H-${nextSemanticRevision.toString().padStart(4, '0')}"
    val hypothesis = Hypothesis(
        id = id,
        missionId = world.mission.id,
        goalId = world.activeGoal.id,
        claim = claim.trim(),
        confidence = confidence,
        unresolved = unresolved.map(String::trim).filter(String::isNotEmpty).distinct().take(6),
    )
    val hypotheses = world.hypotheses.filterNot { it.id == id } + hypothesis
    val evidenceSummary = evidenceRefs.map(String::trim).filter(String::isNotEmpty).distinct().take(8)
    val durable = "${hypothesis.id}: ${hypothesis.claim} (${(hypothesis.confidence * 100).toInt()}%); " +
        if (evidenceSummary.isEmpty()) "sin evidencia vinculada" else "evidencia ${evidenceSummary.joinToString()}"
    return HypothesisProjection(
        world = world.copy(
            worldSeq = world.worldSeq + 1,
            semanticRevision = nextSemanticRevision,
            hypotheses = hypotheses,
        ),
        checkpoint = checkpoint.copy(
            missionId = world.mission.id,
            goalId = world.activeGoal.id,
            durableFindings = (checkpoint.durableFindings.filterNot { it.startsWith("$id:") } + durable)
                .takeLast(8),
            unresolved = hypothesis.unresolved,
        ),
        cognitive = cognitive.copy(
            currentQuestion = hypothesis.unresolved.firstOrNull()
                ?: "¿Qué evidencia puede confirmar o refutar ${hypothesis.id}?",
            lastActionSummary = "Hypothesis ${hypothesis.id} persisted.",
        ),
        hypothesis = hypothesis,
        evidenceRefs = evidenceSummary,
    )
}
