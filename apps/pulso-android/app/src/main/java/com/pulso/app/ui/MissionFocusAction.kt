package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.VisualView
import com.pulso.app.domain.reduceMissionFocus
import com.pulso.app.tools.ActionResult

internal data class MissionFocusOutcome(
    val state: PulsoUiState,
    val result: ActionResult,
)

internal fun applyMissionFocusAction(
    current: PulsoUiState,
    selector: ContextSelector,
    requestedVisual: VisualView?,
    parameters: Map<String, Any>,
): MissionFocusOutcome {
    val title = parameters["title"] as? String
    val successCondition = parameters["success_condition"] as? String
    val reason = parameters["reason"] as? String
    if (title.isNullOrBlank() || successCondition.isNullOrBlank() || reason.isNullOrBlank()) {
        return MissionFocusOutcome(
            current,
            ActionResult(false, "INVALID_ARGUMENT", "A title, success condition, and reason are required."),
        )
    }
    val projection = reduceMissionFocus(
        current.world,
        current.checkpoint,
        current.cognitive,
        title,
        successCondition,
        reason,
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
    return MissionFocusOutcome(
        updated,
        ActionResult(
            true,
            "FOCUS_SET",
            "Mission focus persisted in the checkpoint.",
            mapOf("goal_id" to projection.world.activeGoal.id),
        ),
    )
}
