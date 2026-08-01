package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.VisualView
import com.pulso.app.domain.reduceHypothesis
import com.pulso.app.tools.ActionResult

internal data class HypothesisOutcome(
    val state: PulsoUiState,
    val result: ActionResult,
)

internal fun applyHypothesisAction(
    current: PulsoUiState,
    selector: ContextSelector,
    requestedVisual: VisualView?,
    parameters: Map<String, Any>,
): HypothesisOutcome {
    val id = parameters["hypothesis_id"] as? String
    val claim = parameters["claim"] as? String
    val confidence = (parameters["confidence"] as? Number)?.toFloat()
    val unresolved = (parameters["unresolved"] as? List<*>)?.filterIsInstance<String>()
    val evidenceRefs = (parameters["evidence_refs"] as? List<*>)?.filterIsInstance<String>()
    if (
        id.isNullOrBlank() || claim.isNullOrBlank() || confidence == null || confidence !in 0f..1f ||
        unresolved == null || evidenceRefs == null
    ) {
        return HypothesisOutcome(
            current,
            ActionResult(false, "INVALID_ARGUMENT", "A valid hypothesis payload is required."),
        )
    }
    val projection = reduceHypothesis(
        world = current.world,
        checkpoint = current.checkpoint,
        cognitive = current.cognitive,
        requestedId = id,
        claim = claim,
        confidence = confidence,
        unresolved = unresolved,
        evidenceRefs = evidenceRefs,
    )
    val updated = current.copy(
        world = projection.world,
        checkpoint = projection.checkpoint,
        cognitive = projection.cognitive,
        packet = selector.select(
            projection.world,
            current.decisionNeed,
            projection.cognitive,
            projection.checkpoint,
            requestedVisual,
        ),
    )
    return HypothesisOutcome(
        updated,
        ActionResult(
            true,
            "HYPOTHESIS_SAVED",
            "Hypothesis linked to the active mission and goal.",
            mapOf(
                "hypothesis_id" to projection.hypothesis.id,
                "goal_id" to projection.hypothesis.goalId.orEmpty(),
                "evidence_refs" to projection.evidenceRefs,
            ),
        ),
    )
}
