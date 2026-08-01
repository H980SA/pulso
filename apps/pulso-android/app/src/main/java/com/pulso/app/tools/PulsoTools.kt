package com.pulso.app.tools

import com.google.adk.kt.tools.FunctionTool
import com.google.adk.kt.tools.ToolContext
import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type

class MoveToTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "move_to",
    description = "Navigate safely to one candidate ID from the current WorldPacket.",
) {
    override fun declaration() = targetedDeclaration(name, description)

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val target = targetFrom(args) ?: return invalidTarget()
        return sink.dispatch(
            ActionIntent(
                ActionKind.MOVE_TO,
                target,
                purposeParameters(args),
            )
        ).asMap()
    }
}

class LookAtTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "look_at",
    description = "Rotate the rover chassis to center a current target or viewpoint.",
) {
    override fun declaration() = targetedDeclaration(name, description)

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val target = targetFrom(args) ?: return invalidTarget()
        return sink.dispatch(
            ActionIntent(
                ActionKind.LOOK_AT,
                target,
                purposeParameters(args),
            )
        ).asMap()
    }
}

class RequestViewTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "request_view",
    description = "Request a fresh MetaView or CandidateView for a current candidate ID.",
) {
    override fun declaration() = targetedDeclaration(name, description)

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val target = targetFrom(args) ?: return invalidTarget()
        val viewKind = args["view_kind"] as? String ?: "CANDIDATE_VIEW"
        return sink.dispatch(
            ActionIntent(
                ActionKind.REQUEST_VIEW,
                target,
                purposeParameters(args) + ("view_kind" to viewKind),
            )
        ).asMap()
    }
}

class StopMotionTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "stop_motion",
    description = "Stop rover motion immediately and return the observed stop-attempt status; hardware without ACK remains explicitly unconfirmed.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "reason" to Schema(type = Type.STRING, description = "Why stopping is useful now."),
            ),
            required = listOf("reason"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val reason = (args["reason"] as? String)?.trim().orEmpty()
        if (reason.isBlank()) return invalidArgument("A stop reason is required.")
        return sink.dispatch(
            ActionIntent(ActionKind.STOP, parameters = mapOf("reason" to reason))
        ).asMap()
    }
}

class SetFlashlightTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "set_flashlight",
    description = "Turn the phone flashlight on or off and return confirmed actuator state.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "enabled" to Schema(type = Type.BOOLEAN, description = "Desired flashlight state."),
            ),
            required = listOf("enabled"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val enabled = args["enabled"] as? Boolean
            ?: return mapOf("accepted" to false, "status" to "INVALID_ARGUMENT")
        return sink.dispatch(
            ActionIntent(ActionKind.SET_FLASHLIGHT, parameters = mapOf("enabled" to enabled))
        ).asMap()
    }
}

class SpeakTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "speak",
    description = "Speak a brief phrase through the phone and return confirmed TTS completion.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "text" to Schema(type = Type.STRING, description = "Short phrase to speak aloud."),
                "purpose" to Schema(type = Type.STRING, description = "Mission reason for speaking."),
            ),
            required = listOf("text", "purpose"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val text = (args["text"] as? String)?.trim().orEmpty()
        val purpose = (args["purpose"] as? String)?.trim().orEmpty()
        if (text.isBlank() || purpose.isBlank()) {
            return invalidArgument("Text and purpose are required.")
        }
        if (text.length > MAX_SPEECH_CHARS) {
            return invalidArgument("Speech must be at most $MAX_SPEECH_CHARS characters.")
        }
        return sink.dispatch(
            ActionIntent(
                ActionKind.SPEAK,
                parameters = mapOf("text" to text, "purpose" to purpose),
            )
        ).asMap()
    }

    private companion object {
        const val MAX_SPEECH_CHARS = 240
    }
}

class ListenTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "listen",
    description = "Listen briefly through the phone microphone and return only captured evidence.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "duration_seconds" to Schema(
                    type = Type.INTEGER,
                    description = "Listening window from 1 to 8 seconds.",
                ),
                "purpose" to Schema(type = Type.STRING, description = "Question this audio may answer."),
            ),
            required = listOf("duration_seconds", "purpose"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val duration = (args["duration_seconds"] as? Number)?.toInt()
            ?: return invalidArgument("duration_seconds is required.")
        val purpose = (args["purpose"] as? String)?.trim().orEmpty()
        if (duration !in 1..8 || purpose.isBlank()) {
            return invalidArgument("Use a 1–8 second duration and a non-empty purpose.")
        }
        return sink.dispatch(
            ActionIntent(
                ActionKind.LISTEN,
                parameters = mapOf("duration_seconds" to duration, "purpose" to purpose),
            )
        ).asMap()
    }
}

class SetMissionFocusTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "set_mission_focus",
    description = "Create or replace the active mission goal and return its persistent goal ID.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "title" to Schema(type = Type.STRING, description = "Concise goal title."),
                "success_condition" to Schema(
                    type = Type.STRING,
                    description = "Observable condition that completes the goal.",
                ),
                "reason" to Schema(type = Type.STRING, description = "Why this goal matters now."),
            ),
            required = listOf("title", "success_condition", "reason"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any = sink.dispatch(
        ActionIntent(ActionKind.SET_MISSION_FOCUS, parameters = args)
    ).asMap()
}

class UpdateHypothesisTool(private val sink: PulsoActionSink) : FunctionTool(
    name = "update_hypothesis",
    description = "Persist one testable mission hypothesis with confidence and unresolved evidence needs.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "hypothesis_id" to Schema(
                    type = Type.STRING,
                    description = "Existing hypothesis ID, or NEW to create one.",
                ),
                "claim" to Schema(type = Type.STRING, description = "Concise testable claim."),
                "confidence" to Schema(
                    type = Type.NUMBER,
                    description = "Current confidence from 0.0 to 1.0.",
                ),
                "unresolved" to Schema(
                    type = Type.ARRAY,
                    items = Schema(type = Type.STRING),
                    description = "Concrete questions or evidence still missing.",
                ),
                "evidence_refs" to Schema(
                    type = Type.ARRAY,
                    items = Schema(type = Type.STRING),
                    description = "Artifact or observation IDs supporting this update.",
                ),
            ),
            required = listOf(
                "hypothesis_id",
                "claim",
                "confidence",
                "unresolved",
                "evidence_refs",
            ),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val id = (args["hypothesis_id"] as? String)?.trim().orEmpty()
        val claim = (args["claim"] as? String)?.trim().orEmpty()
        val confidence = (args["confidence"] as? Number)?.toFloat()
            ?: return invalidArgument("confidence is required.")
        val unresolved = args.stringList("unresolved") ?: return invalidArgument("unresolved must be a string list.")
        val evidenceRefs = args.stringList("evidence_refs")
            ?: return invalidArgument("evidence_refs must be a string list.")
        if (id.isBlank() || claim.isBlank() || confidence !in 0f..1f) {
            return invalidArgument("Use an ID, a claim, and confidence from 0.0 to 1.0.")
        }
        return sink.dispatch(
            ActionIntent(
                ActionKind.UPSERT_HYPOTHESIS,
                parameters = mapOf(
                    "hypothesis_id" to id,
                    "claim" to claim,
                    "confidence" to confidence,
                    "unresolved" to unresolved,
                    "evidence_refs" to evidenceRefs,
                ),
            )
        ).asMap()
    }
}

class LoadSkillTool(
    private val skillLibrary: SkillLibrary,
    private val sink: PulsoActionSink,
) : FunctionTool(
    name = "load_skill",
    description = "Load one small procedural skill only when its catalog condition is relevant.",
) {
    override fun declaration() = FunctionDeclaration(
        name = name,
        description = description,
        parameters = Schema(
            type = Type.OBJECT,
            properties = mapOf(
                "skill_id" to Schema(
                    type = Type.STRING,
                    description = "Skill ID from the system catalog.",
                    enum = skillLibrary.catalog().map { it.id },
                ),
                "reason" to Schema(type = Type.STRING, description = "Why it is needed now."),
            ),
            required = listOf("skill_id", "reason"),
        ),
    )

    override suspend fun execute(context: ToolContext, args: Map<String, Any>): Any {
        val skillId = args["skill_id"] as? String
            ?: return mapOf("accepted" to false, "status" to "INVALID_ARGUMENT")
        val skill = skillLibrary.load(skillId)
            ?: return mapOf("accepted" to false, "status" to "UNKNOWN_SKILL")
        val result = sink.dispatch(
            ActionIntent(ActionKind.LOAD_SKILL, parameters = mapOf("skill_id" to skillId))
        )
        return result.asMap() + mapOf(
            "skill_id" to skill.id,
            "when_useful" to skill.whenUseful,
            "instructions" to skill.instructions,
        )
    }
}

private fun targetedDeclaration(name: String, description: String) = FunctionDeclaration(
    name = name,
    description = description,
    parameters = Schema(
        type = Type.OBJECT,
        properties = mapOf(
            "target_type" to Schema(
                type = Type.STRING,
                enum = listOf("VIEWPOINT", "FRONTIER", "TARGET", "ANCHOR"),
                description = "Type shown beside the candidate ID.",
            ),
            "target_id" to Schema(type = Type.STRING, description = "Exact current candidate ID."),
            "view_kind" to Schema(
                type = Type.STRING,
                enum = listOf("META_VIEW", "CANDIDATE_VIEW", "TARGET_VIEW"),
                description = "Used only by request_view.",
            ),
            "purpose" to Schema(
                type = Type.STRING,
                description = "Mission reason for this action.",
            ),
        ),
        required = listOf("target_type", "target_id", "purpose"),
    ),
)

private fun targetFrom(args: Map<String, Any>): com.pulso.app.domain.CandidateId? {
    val kind = args["target_type"] as? String ?: return null
    val id = args["target_id"] as? String ?: return null
    return parseCandidate(kind, id)
}

private fun invalidTarget() = mapOf(
    "accepted" to false,
    "status" to "INVALID_TARGET",
    "detail" to "Use an exact typed candidate ID from the current WorldPacket.",
)

private fun invalidArgument(detail: String) = mapOf(
    "accepted" to false,
    "status" to "INVALID_ARGUMENT",
    "detail" to detail,
)

private fun purposeParameters(args: Map<String, Any>): Map<String, Any> = mapOf(
    "purpose" to ((args["purpose"] as? String)?.trim().orEmpty()),
)

private fun Map<String, Any>.stringList(key: String): List<String>? {
    val values = this[key] as? List<*> ?: return null
    return values.mapNotNull { (it as? String)?.trim()?.takeIf(String::isNotEmpty) }
        .takeIf { it.size == values.size }
}
