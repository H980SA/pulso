package com.pulso.app.runtime

/**
 * Public, bounded decision evidence for the operator dashboard.
 *
 * This is deliberately not a serialization of ADK events. Tool responses may
 * contain skill instructions or opaque capabilities, and model internals are
 * not operator evidence. Only fields that explain an observable decision are
 * allowed through this projection.
 */
internal data class BrainTelemetryRecord(
    val turnId: String?,
    val selectedWorldSeq: Long?,
    val category: String,
    val label: String,
    val summary: String,
    val latencyMs: Long? = null,
    val attributes: Map<String, Any> = emptyMap(),
)

internal fun BrainTraceEvent.toTelemetryRecord(): BrainTelemetryRecord = when (this) {
    is BrainTraceEvent.PacketSelected -> BrainTelemetryRecord(
        turnId = turnId,
        selectedWorldSeq = selectedWorldSeq,
        category = "CONTEXT",
        label = "WorldPacket selected",
        summary = "$decisionNeed · $candidateCount current candidates",
        attributes = buildMap {
            put("candidate_count", candidateCount)
            put("decision_need", publicText(decisionNeed, 80))
            put("goal_id", publicText(goalId, 96))
            put("checkpoint", publicText(checkpointSummary, 160))
            put("question", publicText(question, 360))
            put("plan_summary", publicText(planSummary, 360))
            activeSkillId?.let { put("active_skill_id", publicText(it, 96)) }
        },
    )

    is BrainTraceEvent.ToolRequested -> {
        val safe = safeToolArguments(name, arguments)
        BrainTelemetryRecord(
            turnId = turnId,
            selectedWorldSeq = selectedWorldSeq,
            category = "TOOL_REQUEST",
            label = name,
            summary = safe.entries.joinToString(" · ") { "${it.key}=${it.value}" }
                .ifBlank { "No public arguments" },
            attributes = safe,
        )
    }

    is BrainTraceEvent.ToolCompleted -> {
        val safe = safeToolResult(response)
        val status = safe["status"]?.toString()
        val detail = safe["detail"]?.toString()
        BrainTelemetryRecord(
            turnId = turnId,
            selectedWorldSeq = selectedWorldSeq,
            category = "TOOL_RESULT",
            label = name,
            summary = listOfNotNull(status, detail).joinToString(" · ")
                .ifBlank { "Tool completed" },
            attributes = safe,
        )
    }

    is BrainTraceEvent.Response -> BrainTelemetryRecord(
        turnId = turnId,
        selectedWorldSeq = selectedWorldSeq,
        category = "MODEL_RESPONSE",
        label = "Gemma decision",
        summary = publicText(text, 900),
    )

    is BrainTraceEvent.CycleCompleted -> BrainTelemetryRecord(
        turnId = turnId,
        selectedWorldSeq = selectedWorldSeq,
        category = "CYCLE_COMPLETE",
        label = "Decision cycle complete",
        summary = "${latencyMs}ms end to end",
        latencyMs = latencyMs.coerceAtLeast(0),
    )

    is BrainTraceEvent.Canceled -> BrainTelemetryRecord(
        turnId = turnId,
        selectedWorldSeq = selectedWorldSeq,
        category = "CANCELED",
        label = "Decision turn canceled",
        summary = publicText(reason, 360),
    )

    is BrainTraceEvent.Failure -> BrainTelemetryRecord(
        turnId = turnId,
        selectedWorldSeq = selectedWorldSeq,
        category = "ERROR",
        label = "Agent runtime",
        summary = publicText(detail, 500),
    )
}

private fun safeToolArguments(name: String, values: Map<String, Any?>): Map<String, Any> {
    val allowed = when (name) {
        "move_to", "look_at" -> setOf("target_type", "target_id", "purpose")
        "request_view" -> setOf("target_type", "target_id", "view_kind", "purpose")
        "stop_motion" -> setOf("reason")
        "set_flashlight" -> setOf("enabled")
        "speak" -> setOf("text", "purpose")
        "listen" -> setOf("duration_seconds", "purpose")
        "set_mission_focus" -> setOf("title", "success_condition", "reason")
        "update_hypothesis" -> setOf("hypothesis_id", "claim", "confidence")
        "load_skill" -> setOf("skill_id", "reason")
        "complete_mission" -> setOf(
            "mission_id",
            "goal_id",
            "completion_summary",
            "evidence_refs",
            "remaining_risks",
        )
        else -> emptySet()
    }
    return publicFields(values, allowed)
}

private fun safeToolResult(values: Map<String, Any?>): Map<String, Any> = publicFields(
    values,
    setOf(
        "accepted",
        "status",
        "detail",
        "action_id",
        "target_id",
        "candidate_id",
        "requested_target_type",
        "requested_target_id",
        "resolved_target_type",
        "resolved_target_id",
        "target_id_canonicalized",
        "navigation_revision",
        "reason",
        "enabled",
        "skill_id",
        "goal_id",
        "hypothesis_id",
        "mission_id",
        "evidence_count",
        "remaining_risk_count",
        "artifact_topic",
        "view_kind",
    ),
)

private fun publicFields(values: Map<String, Any?>, allowed: Set<String>): Map<String, Any> =
    buildMap {
        allowed.forEach { key ->
            when (val value = values[key]) {
                is Boolean -> put(key, value)
                is Number -> put(key, value)
                is String -> put(key, publicText(value, if (key == "detail") 360 else 160))
                is List<*> -> put(
                    key,
                    value.mapNotNull { (it as? String)?.let { text -> publicText(text, 160) } }
                        .take(12)
                        .joinToString(" | "),
                )
            }
        }
    }

private fun publicText(value: String, maxLength: Int): String = value
    .replace(Regex("[\\p{Cc}\\p{Cf}]+"), " ")
    .replace(Regex("\\s+"), " ")
    .trim()
    .take(maxLength)
