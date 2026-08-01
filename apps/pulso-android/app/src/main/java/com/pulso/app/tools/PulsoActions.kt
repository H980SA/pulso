package com.pulso.app.tools

import com.pulso.app.domain.CandidateId
import com.pulso.app.domain.CandidateKind
import com.pulso.app.domain.Candidate

enum class ActionKind {
    STOP,
    MOVE_TO,
    LOOK_AT,
    REQUEST_VIEW,
    SET_FLASHLIGHT,
    SPEAK,
    LISTEN,
    SET_MISSION_FOCUS,
    UPSERT_HYPOTHESIS,
    LOAD_SKILL,
    COMPLETE_MISSION,
}

data class ActionIntent(
    val kind: ActionKind,
    val target: CandidateId? = null,
    val parameters: Map<String, Any> = emptyMap(),
    val candidateCapability: String? = null,
    val expectedNavigationRevision: Long? = null,
    val expectedTrackingEpoch: Long? = null,
    val expectedTargetRevision: Long? = null,
)

data class ActionResult(
    val accepted: Boolean,
    val status: String,
    val detail: String,
    val data: Map<String, Any> = emptyMap(),
) {
    fun asMap(): Map<String, Any> = buildMap {
        put("accepted", accepted)
        put("status", status)
        put("detail", detail)
        putAll(data)
    }
}

interface PulsoActionSink {
    suspend fun dispatch(intent: ActionIntent): ActionResult
}

class GuardedActionSink(
    private val delegate: PulsoActionSink,
) : PulsoActionSink {
    @Volatile
    private var allowedTargets: Map<CandidateId, Candidate> = emptyMap()
    @Volatile
    private var turnActive: Boolean = false

    fun beginTurn(candidates: List<Candidate>) {
        allowedTargets = candidates.associateBy { it.id }
        turnActive = true
    }

    /** Backward-compatible test/harness entrypoint; production uses beginTurn. */
    fun updateAllowedCandidates(candidates: List<Candidate>) = beginTurn(candidates)

    fun invalidateTurn() {
        turnActive = false
        allowedTargets = emptyMap()
    }

    override suspend fun dispatch(intent: ActionIntent): ActionResult {
        if (!turnActive) {
            return ActionResult(
                false,
                "CANCELED_TURN",
                "This Gemma turn is no longer active; no late tool call may change state.",
            )
        }
        if (intent.kind in TARGETED_ACTIONS) {
            val target = intent.target
                ?: return ActionResult(false, "REJECTED", "A typed target ID is required.")
            val audit = mapOf(
                "requested_target_type" to target.kind.name,
                "requested_target_id" to target.value,
            )
            if (intent.kind == ActionKind.MOVE_TO && target.kind == CandidateKind.TARGET) {
                return ActionResult(
                    accepted = false,
                    status = "TARGET_TYPE_MISMATCH",
                    detail = "TARGET candidates never authorize MOVE_TO.",
                    data = audit,
                )
            }
            val resolution = resolveCurrentCandidate(target, allowedTargets.values)
            val candidate = resolution.candidate
            if (candidate == null) {
                return ActionResult(
                    accepted = false,
                    status = if (resolution.ambiguous) "AMBIGUOUS_TARGET_ID" else "STALE_OR_UNKNOWN_TARGET",
                    detail = if (resolution.ambiguous) {
                        "${target.kind}:${target.value} matches more than one current candidate."
                    } else {
                        "${target.kind}:${target.value} is not valid in the current WorldPacket."
                    },
                    data = audit,
                )
            }
            val resolvedIntent = intent.copy(
                target = candidate.id,
                candidateCapability = candidate.capability,
                expectedNavigationRevision = candidate.navigationRevision,
                expectedTrackingEpoch = candidate.trackingEpoch,
                expectedTargetRevision = candidate.targetRevision,
            )
            val result = delegate.dispatch(
                resolvedIntent
            )
            return result.copy(data = result.data + audit + mapOf(
                "resolved_target_type" to candidate.id.kind.name,
                "resolved_target_id" to candidate.id.value,
                "target_id_canonicalized" to resolution.canonicalized,
            ))
        }
        return delegate.dispatch(intent)
    }

    private companion object {
        val TARGETED_ACTIONS = setOf(ActionKind.MOVE_TO, ActionKind.LOOK_AT, ActionKind.REQUEST_VIEW)
    }
}

internal data class CurrentCandidateResolution(
    val candidate: Candidate?,
    val canonicalized: Boolean = false,
    val ambiguous: Boolean = false,
)

/**
 * Conservative repair for formatting drift only. Exact IDs win; otherwise signed integer tokens
 * may differ in zero padding, or the requested token sequence may be a unique structural prefix.
 */
internal fun resolveCurrentCandidate(
    requested: CandidateId,
    current: Collection<Candidate>,
): CurrentCandidateResolution {
    current.firstOrNull { it.id == requested }?.let { return CurrentCandidateResolution(it) }
    val requestedTokens = canonicalIdTokens(requested.value) ?: return CurrentCandidateResolution(null)
    val sameKind = current.filter { it.id.kind == requested.kind }
    val normalizedMatches = sameKind.filter { canonicalIdTokens(it.id.value) == requestedTokens }
    if (normalizedMatches.size == 1) return CurrentCandidateResolution(normalizedMatches.single(), canonicalized = true)
    if (normalizedMatches.size > 1) return CurrentCandidateResolution(null, ambiguous = true)
    if (requestedTokens.size < 2) return CurrentCandidateResolution(null)
    val prefixMatches = sameKind.filter { candidate ->
        val tokens = canonicalIdTokens(candidate.id.value) ?: return@filter false
        tokens.size > requestedTokens.size && tokens.take(requestedTokens.size) == requestedTokens
    }
    return when (prefixMatches.size) {
        1 -> CurrentCandidateResolution(prefixMatches.single(), canonicalized = true)
        0 -> CurrentCandidateResolution(null)
        else -> CurrentCandidateResolution(null, ambiguous = true)
    }
}

private fun canonicalIdTokens(value: String): List<String>? {
    val trimmed = value.trim()
    if (!trimmed.matches(Regex("[A-Za-z]+(?:[_:.-][+-]?\\d+)+"))) return null
    val tokens = mutableListOf<String>()
    for (match in Regex("[A-Za-z]+|[+-]?\\d+").findAll(trimmed)) {
        val token = match.value
        tokens += if (token.first().isLetter()) {
            token.uppercase()
        } else {
            token.toLongOrNull()?.toString() ?: return null
        }
    }
    return tokens
}

fun parseCandidate(kind: String, id: String): CandidateId? {
    val parsedKind = runCatching { CandidateKind.valueOf(kind.uppercase()) }.getOrNull() ?: return null
    if (id.isBlank()) return null
    return CandidateId(parsedKind, id)
}
