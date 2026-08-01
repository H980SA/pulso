package com.pulso.app.tools

import com.google.adk.kt.tools.FunctionTool
import com.google.adk.kt.tools.ToolContext
import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type

class CompleteMissionTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "complete_mission",
    description = "End autonomy only when the root mission success condition is satisfied by current evidence.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "mission_id" to Schema(type = Type.STRING, description = "Exact current root mission ID."),
                "goal_id" to Schema(
                    type = Type.STRING,
                    description = "Exact current active goal ID used to ground this decision.",
                ),
                "completion_summary" to Schema(
                    type = Type.STRING,
                    description = "Brief public explanation of why the root mission is complete.",
                ),
                "evidence_refs" to Schema(
                    type = Type.ARRAY,
                    items = Schema(type = Type.STRING),
                    description = "One or more exact current evidence IDs supporting completion.",
                ),
                "remaining_risks" to Schema(
                    type = Type.ARRAY,
                    items = Schema(type = Type.STRING),
                    description = "Known residual risks; use an empty list only when none remain.",
                ),
            ),
            required = listOf(
                "mission_id",
                "goal_id",
                "completion_summary",
                "evidence_refs",
                "remaining_risks",
            ),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val missionId = (args["mission_id"] as? String)?.trim().orEmpty()
        val goalId = (args["goal_id"] as? String)?.trim().orEmpty()
        val summary = (args["completion_summary"] as? String)?.trim().orEmpty()
        val evidenceRefs = args.stringList("evidence_refs")
            ?: return invalid("evidence_refs must be a string list.")
        val remainingRisks = args.stringList("remaining_risks")
            ?: return invalid("remaining_risks must be a string list.")
        if (missionId.isBlank() || goalId.isBlank() || summary.isBlank() || evidenceRefs.isEmpty()) {
            return invalid("Use current mission/goal IDs, a summary, and at least one evidence ref.")
        }
        return sink.dispatch(
            ActionIntent(
                ActionKind.COMPLETE_MISSION,
                parameters = mapOf(
                    "mission_id" to missionId,
                    "goal_id" to goalId,
                    "completion_summary" to summary,
                    "evidence_refs" to evidenceRefs,
                    "remaining_risks" to remainingRisks,
                ),
            )
        ).asMap()
    }
}

private fun invalid(detail: String) = mapOf(
    "accepted" to false,
    "status" to "INVALID_ARGUMENT",
    "detail" to detail,
)

private fun Map<String, Any>.stringList(key: String): List<String>? {
    val values = this[key] as? List<*> ?: return null
    return values.mapNotNull { (it as? String)?.trim()?.takeIf(String::isNotEmpty) }
        .takeIf { it.size == values.size }
}
