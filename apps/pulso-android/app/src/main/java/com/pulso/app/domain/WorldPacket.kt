package com.pulso.app.domain

enum class DecisionNeed(val requiresVisualView: Boolean) {
    MONITOR(false),
    CHOOSE_ROUTE(true),
    INSPECT_TARGET(true),
    RECOVER_TRACKING(false),
}

data class CognitiveState(
    val currentQuestion: String,
    val planSummary: String,
    val activeSkillId: String?,
    val lastActionSummary: String?,
)

data class MissionCheckpoint(
    val missionId: String,
    val goalId: String,
    val durableFindings: List<String>,
    val rejectedAlternatives: List<String>,
    val unresolved: List<String>,
)

data class VisualView(
    val artifactId: String,
    val kind: String,
    val navigationRevision: Long,
    /** ID of the accepted request_view action that authorized this one-turn attachment. */
    val requestActionId: String = "",
    val capturedAtMonotonicMs: Long? = null,
    val targetId: CandidateId? = null,
    val targetRevision: Long? = null,
    val jpegBytes: ByteArray? = null,
)

data class WorldPacket(
    val worldSeq: Long,
    val decisionNeed: DecisionNeed,
    val brief: String,
    val candidates: List<Candidate>,
    val visualView: VisualView?,
    val checkpoint: MissionCheckpoint,
    val cognitiveState: CognitiveState,
) {
    fun toPrompt(): String = buildString {
        appendLine("CURRENT WORLD PACKET")
        appendLine(brief)
        appendLine()
        appendLine("Candidate IDs you may reference:")
        if (candidates.isEmpty()) {
            appendLine("- NONE. Do not invent, reuse, or guess a candidate ID.")
        } else {
            candidates.forEach { candidate ->
                append("- ${candidate.id.kind}:${candidate.id.value} — ${candidate.label}; ")
                append("purpose=${candidate.purpose}; path=${"%.2f".format(candidate.pathLengthM)}m; ")
                appendLine("risk=${"%.2f".format(candidate.risk)}; info_gain=${"%.2f".format(candidate.informationGain)}")
            }
        }
        if (visualView != null) {
            appendLine("Visual view attached: ${visualView.kind} ${visualView.artifactId}.")
        } else {
            appendLine("No visual view is attached for this decision.")
        }
        appendLine("Checkpoint goal: ${checkpoint.goalId}.")
        checkpoint.durableFindings.forEach { appendLine("Known: $it") }
        checkpoint.unresolved.forEach { appendLine("Unresolved: $it") }
        appendLine("Current question: ${cognitiveState.currentQuestion}")
        appendLine("Current plan: ${cognitiveState.planSummary}")
        appendLine("Choose the next useful action. Use a tool for any state change or physical action.")
        appendLine("Only complete_mission ends autonomy; finishing a frontier, view, target inspection, or active goal does not.")
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is WorldPacket) return false
        return worldSeq == other.worldSeq &&
            decisionNeed == other.decisionNeed &&
            brief == other.brief &&
            candidates == other.candidates &&
            visualView?.artifactId == other.visualView?.artifactId &&
            visualView?.requestActionId == other.visualView?.requestActionId &&
            checkpoint == other.checkpoint &&
            cognitiveState == other.cognitiveState
    }

    override fun hashCode(): Int = listOf(
        worldSeq,
        decisionNeed,
        brief,
        candidates,
        visualView?.artifactId,
        visualView?.requestActionId,
        checkpoint,
        cognitiveState,
    ).hashCode()
}
