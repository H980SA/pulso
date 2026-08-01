package com.pulso.app.runtime

import com.pulso.app.domain.WorldPacket
import java.security.MessageDigest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Immutable-at-the-boundary snapshot of the user content passed to one Gemma turn.
 *
 * The runtime builds this once, publishes it as operator evidence, and then uses
 * the same prompt string and JPEG byte array to construct ADK's Content object.
 */
data class GemmaTurnInput(
    val inputId: String,
    val turnId: String,
    val selectedWorldSeq: Long,
    val modelId: String,
    val inputKind: String,
    val exactMessage: JsonObject,
    val promptText: String?,
    val image: GemmaVisualInput?,
    val systemPrompt: String,
    val systemPromptSha256: String,
    val toolSchemas: JsonArray,
    val toolSchemasSha256: String,
    val conversationScope: String = "TURN",
    val conversationReusedWithinTurn: Boolean = true,
    val conversationReusedAcrossTurns: Boolean = false,
)

data class GemmaVisualInput(
    val artifactId: String,
    val kind: String,
    val sourceTopic: String,
    val capturedMonotonicNs: Long,
    val format: String,
    val jpegSha256: String,
    val byteLength: Int,
    val auditTopic: String,
    val jpegBytes: ByteArray,
)

data class GemmaToolResponseInput(
    val name: String,
    val response: Map<String, Any?>,
)

internal fun prepareGemmaTurnInput(
    packet: WorldPacket,
    turnId: String,
    systemPrompt: String,
    toolContracts: ToolContractSnapshot,
): GemmaTurnInput {
    val view = packet.visualView
    require(view == null || view.requestActionId.isNotBlank()) {
        "Visual input is not authorized by a successful request_view action."
    }
    val visual = view?.let {
        val bytes = requireNotNull(it.jpegBytes)
            .takeIf(ByteArray::isNotEmpty)
            ?: throw IllegalArgumentException("Authorized visual input has no JPEG bytes.")
        GemmaVisualInput(
            artifactId = it.artifactId,
            kind = if (it.kind == "META_VIEW") "META_VIEW" else "EGO_RGB",
            sourceTopic = if (it.kind == "META_VIEW") {
                "/pulso/navigation/metaview/compressed"
            } else {
                "/pulso/phone/rgb/compressed"
            },
            capturedMonotonicNs = (it.capturedAtMonotonicMs ?: 0L) * 1_000_000L,
            format = "jpeg",
            jpegSha256 = sha256Hex(bytes),
            byteLength = bytes.size,
            auditTopic = GEMMA_VIEW_AUDIT_TOPIC,
            jpegBytes = bytes,
        )
    }
    val promptText = packet.toPrompt()
    val exactMessage = buildJsonObject {
        put("role", "user")
        put(
            "parts",
            buildJsonArray {
                add(buildJsonObject {
                    put("index", 0)
                    put("kind", "text")
                    put("text", promptText)
                })
                visual?.let { image ->
                    add(buildJsonObject {
                        put("index", 1)
                        put("kind", "inline_data")
                        put("mime_type", GEMMA_VISUAL_MIME_TYPE)
                        put("byte_length", image.byteLength)
                        put("jpeg_sha256", image.jpegSha256)
                        put("audit_topic", image.auditTopic)
                    })
                }
            },
        )
    }
    return GemmaTurnInput(
        inputId = "IN-$turnId",
        turnId = turnId,
        selectedWorldSeq = packet.worldSeq,
        modelId = PULSO_GEMMA_MODEL_ID,
        inputKind = "WORLD_PACKET",
        exactMessage = exactMessage,
        promptText = promptText,
        image = visual,
        systemPrompt = systemPrompt,
        systemPromptSha256 = sha256Hex(systemPrompt.toByteArray(Charsets.UTF_8)),
        toolSchemas = toolContracts.schemas,
        toolSchemasSha256 = toolContracts.sha256,
    )
}

internal fun prepareGemmaToolResultInput(
    initialInput: GemmaTurnInput,
    sequence: Int,
    responses: List<GemmaToolResponseInput>,
): GemmaTurnInput {
    require(responses.isNotEmpty()) { "At least one tool response is required." }
    val exactMessage = buildJsonObject {
        put("role", "tool")
        put(
            "parts",
            buildJsonArray {
                responses.forEachIndexed { index, response ->
                    add(buildJsonObject {
                        put("index", index)
                        put("kind", "function_response")
                        put("name", response.name)
                        put("response", response.response.toExactJsonElement())
                    })
                }
            },
        )
    }
    return initialInput.copy(
        inputId = "${initialInput.inputId}-TOOL-$sequence",
        inputKind = "TOOL_RESULT",
        exactMessage = exactMessage,
        promptText = null,
        image = null,
    )
}

data class ToolContractSnapshot(
    val schemas: JsonArray,
    val sha256: String,
)

internal fun sha256Hex(bytes: ByteArray): String = MessageDigest
    .getInstance("SHA-256")
    .digest(bytes)
    .joinToString("") { byte -> "%02x".format(byte) }

private fun Any?.toExactJsonElement(): JsonElement = when (this) {
    null -> JsonNull
    is JsonElement -> this
    is Boolean -> JsonPrimitive(this)
    is Number -> JsonPrimitive(this)
    is String -> JsonPrimitive(this)
    is Map<*, *> -> buildJsonObject {
        this@toExactJsonElement.forEach { (key, value) ->
            put(key.toString(), value.toExactJsonElement())
        }
    }
    is Iterable<*> -> buildJsonArray {
        this@toExactJsonElement.forEach { add(it.toExactJsonElement()) }
    }
    is Array<*> -> buildJsonArray {
        this@toExactJsonElement.forEach { add(it.toExactJsonElement()) }
    }
    else -> JsonPrimitive(toString())
}

/** Preserves the one-way evidence order while keeping telemetry best effort. */
internal suspend fun <T> runAfterGemmaInputPublished(
    input: GemmaTurnInput,
    publishInput: (GemmaTurnInput) -> Unit,
    inference: suspend () -> T,
): T {
    runCatching { publishInput(input) }
    return inference()
}

const val PULSO_GEMMA_MODEL_ID = "gemma-4-e4b-it-litertlm"
const val GEMMA_VISUAL_MIME_TYPE = "image/jpeg"
const val GEMMA_VIEW_AUDIT_TOPIC = "/pulso/hil/gemma_view/compressed"
