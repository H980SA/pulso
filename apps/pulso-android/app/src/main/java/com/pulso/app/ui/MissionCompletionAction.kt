package com.pulso.app.ui

import com.pulso.app.tools.ActionResult

data class MissionCompletion(
    val missionId: String,
    val goalId: String,
    val completionSummary: String,
    val evidenceRefs: List<String>,
    val remainingRisks: List<String>,
    val completedAtMonotonicMs: Long,
)

internal data class MissionCompletionOutcome(
    val state: PulsoUiState,
    val result: ActionResult,
)

/**
 * Grounds Gemma's semantic completion decision in the exact active mission and evidence IDs.
 * This gate deliberately does not decide whether the mission is semantically complete: Gemma does.
 */
internal fun applyMissionCompletionAction(
    current: PulsoUiState,
    parameters: Map<String, Any>,
): MissionCompletionOutcome {
    if (current.missionCompletion != null) {
        return MissionCompletionOutcome(
            current,
            ActionResult(false, "MISSION_ALREADY_COMPLETE", "The active mission was already completed."),
        )
    }
    val missionId = (parameters["mission_id"] as? String)?.trim().orEmpty()
    val goalId = (parameters["goal_id"] as? String)?.trim().orEmpty()
    val summary = (parameters["completion_summary"] as? String)?.trim().orEmpty()
    val evidenceRefs = parameters.stringList("evidence_refs")
    val remainingRisks = parameters.stringList("remaining_risks")
    if (missionId.isBlank() || goalId.isBlank() || summary.isBlank() ||
        evidenceRefs == null || remainingRisks == null
    ) {
        return MissionCompletionOutcome(
            current,
            ActionResult(
                false,
                "INVALID_ARGUMENT",
                "mission_id, goal_id, completion_summary, evidence_refs, and remaining_risks are required.",
            ),
        )
    }
    if (missionId != current.world.mission.id || goalId != current.world.activeGoal.id) {
        return MissionCompletionOutcome(
            current,
            ActionResult(
                false,
                "STALE_MISSION_CONTEXT",
                "Completion must reference the exact current mission and active goal IDs.",
                mapOf(
                    "mission_id" to current.world.mission.id,
                    "goal_id" to current.world.activeGoal.id,
                ),
            ),
        )
    }
    if (evidenceRefs.isEmpty()) {
        return MissionCompletionOutcome(
            current,
            ActionResult(false, "EVIDENCE_REQUIRED", "At least one current evidence reference is required."),
        )
    }
    val knownEvidence = buildSet {
        current.world.artifacts.forEach { add(it.id) }
        current.world.targets.forEach { addAll(it.evidenceIds) }
        current.packet.visualView?.artifactId?.let(::add)
    }
    val unknown = evidenceRefs.distinct().filterNot(knownEvidence::contains)
    if (unknown.isNotEmpty()) {
        return MissionCompletionOutcome(
            current,
            ActionResult(
                false,
                "UNKNOWN_EVIDENCE_REF",
                "Completion referenced evidence that is not current: ${unknown.joinToString(", ")}.",
                mapOf("known_evidence_count" to knownEvidence.size),
            ),
        )
    }
    val completion = MissionCompletion(
        missionId = missionId,
        goalId = goalId,
        completionSummary = summary,
        evidenceRefs = evidenceRefs.distinct(),
        remainingRisks = remainingRisks.distinct(),
        completedAtMonotonicMs = current.world.monotonicNowMs,
    )
    return MissionCompletionOutcome(
        current.copy(
            missionCompletion = completion,
            autonomyEnabled = false,
            cognitive = current.cognitive.copy(
                currentQuestion = "Misión completada por Gemma y validada contra evidencia vigente.",
                planSummary = summary,
                lastActionSummary = "Mission ${missionId} completed.",
            ),
        ),
        ActionResult(
            true,
            "MISSION_COMPLETED",
            summary,
            mapOf(
                "mission_id" to missionId,
                "goal_id" to goalId,
                "evidence_count" to completion.evidenceRefs.size,
                "remaining_risk_count" to completion.remainingRisks.size,
            ),
        ),
    )
}

private fun Map<String, Any>.stringList(key: String): List<String>? {
    val values = this[key] as? List<*> ?: return null
    return values.mapNotNull { (it as? String)?.trim()?.takeIf(String::isNotEmpty) }
        .takeIf { it.size == values.size }
}
