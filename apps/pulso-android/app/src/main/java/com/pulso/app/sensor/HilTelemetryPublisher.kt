package com.pulso.app.sensor

import com.pulso.app.runtime.BrainTelemetryRecord
import com.pulso.app.runtime.GemmaTurnInput
import java.util.Base64
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.WebSocket

/** Publishes read-only operator evidence without participating in cognition. */
internal class HilTelemetryPublisher(
    private val socketProvider: () -> WebSocket?,
) {
    fun publishPerceptionTracks(
        capturedMonotonicNs: Long,
        tracks: List<PerceptionTrackObservation>,
    ): Boolean {
        val payload = buildJsonObject {
            put("contract_version", "pulso.perception.tracks.v1")
            put("captured_monotonic_ns", capturedMonotonicNs)
            put("frame_id", "phone_camera_optical_frame")
            put(
                "tracks",
                JsonArray(tracks.map { track ->
                    buildJsonObject {
                        put("id", track.id)
                        put("label", track.label)
                        put("model_id", track.modelId)
                        put("confidence", track.confidence)
                        put("bearing_deg", track.bearingDeg)
                        put(
                            "box_norm",
                            JsonArray(
                                listOf(
                                    track.leftNorm,
                                    track.topNorm,
                                    track.rightNorm,
                                    track.bottomNorm,
                                ).map(::JsonPrimitive)
                            ),
                        )
                        put("revision", track.revision)
                        put("inference_latency_ms", track.inferenceLatencyMs)
                        put("visible_keypoints", track.visibleKeypoints)
                    }
                }),
            )
        }
        return publishString("/pulso/hil/perception_tracks", payload)
    }

    fun publishBrainTrace(record: BrainTelemetryRecord): Boolean {
        val payload = buildJsonObject {
            put("contract_version", "pulso.brain-trace.v1")
            put("event_id", "BT-${System.nanoTime()}")
            put("captured_monotonic_ns", System.nanoTime())
            record.turnId?.let { put("turn_id", it) }
            record.selectedWorldSeq?.let { put("selected_world_seq", it) }
            put("category", record.category)
            put("label", record.label)
            put("summary", record.summary)
            record.latencyMs?.let { put("latency_ms", it) }
            put(
                "attributes",
                JsonObject(record.attributes.mapValues { (_, value) -> value.toJsonElement() }),
            )
        }
        return publishString("/pulso/hil/brain_trace", payload)
    }

    fun publishPerceptionTelemetry(
        sourceCaptureNs: Long,
        modelId: String,
        status: String,
        detectionCount: Int,
        inferenceLatencyMs: Long,
        semanticRevision: Long,
    ): Boolean {
        val payload = buildJsonObject {
            put("contract_version", "pulso.perception-telemetry.v1")
            put("published_monotonic_ns", System.nanoTime())
            put("source_capture_ns", sourceCaptureNs)
            put("model_id", modelId)
            put("status", status)
            put("detection_count", detectionCount.coerceAtLeast(0))
            put("inference_latency_ms", inferenceLatencyMs.coerceAtLeast(0))
            put("semantic_revision", semanticRevision.coerceAtLeast(0))
        }
        return publishString("/pulso/hil/perception_telemetry", payload)
    }

    /**
     * Enqueues the exact initial turn content before inference starts.
     * The optional CompressedImage is encoded from the same ByteArray later
     * passed to ADK; neither serialization path can alter cognition.
     */
    fun publishGemmaInput(input: GemmaTurnInput): Boolean {
        val activeSocket = socketProvider() ?: return false
        val publishedNs = System.nanoTime()
        val inputSent = activeSocket.send(
            rosbridgeStringPublish(
                "/pulso/hil/gemma_input",
                gemmaInputPayload(input, publishedNs),
            ).toString()
        )
        val viewMessage = gemmaViewMessage(input, publishedNs)
        val viewSent = viewMessage == null || activeSocket.send(
            rosbridgeMessagePublish("/pulso/hil/gemma_view/compressed", viewMessage).toString()
        )
        return inputSent && viewSent
    }

    private fun publishString(topic: String, payload: JsonObject): Boolean {
        val activeSocket = socketProvider() ?: return false
        return activeSocket.send(rosbridgeStringPublish(topic, payload).toString())
    }
}

internal fun gemmaInputPayload(input: GemmaTurnInput, publishedMonotonicNs: Long): JsonObject =
    buildJsonObject {
        put("contract_version", "pulso.gemma-input.v1")
        put("input_id", input.inputId)
        put("published_monotonic_ns", publishedMonotonicNs)
        put("turn_id", input.turnId)
        put("selected_world_seq", input.selectedWorldSeq)
        put("model_id", input.modelId)
        put("input_kind", input.inputKind)
        put("exact_message", input.exactMessage)
        put("prompt_text", input.promptText?.let(::JsonPrimitive) ?: JsonNull)
        put("system_prompt", input.systemPrompt)
        put("system_prompt_sha256", input.systemPromptSha256)
        put("tool_schemas", input.toolSchemas)
        put("tool_schemas_sha256", input.toolSchemasSha256)
        put("conversation_scope", input.conversationScope)
        put("conversation_reused_within_turn", input.conversationReusedWithinTurn)
        put("conversation_reused_across_turns", input.conversationReusedAcrossTurns)
        put(
            "image",
            input.image?.let { image ->
                buildJsonObject {
                    put("kind", image.kind)
                    put("source_topic", image.sourceTopic)
                    put("captured_monotonic_ns", image.capturedMonotonicNs)
                    put("format", image.format)
                    put("jpeg_sha256", image.jpegSha256)
                    put("byte_length", image.byteLength)
                    put("audit_topic", image.auditTopic)
                }
            } ?: JsonNull,
        )
    }

internal fun gemmaViewMessage(
    input: GemmaTurnInput,
    publishedMonotonicNs: Long,
): JsonObject? {
    val visual = input.image ?: return null
    return buildJsonObject {
        put(
            "header",
            buildJsonObject {
                put(
                    "stamp",
                    buildJsonObject {
                        put("sec", publishedMonotonicNs / 1_000_000_000L)
                        put("nanosec", publishedMonotonicNs % 1_000_000_000L)
                    },
                )
                put("frame_id", "gemma_input_view")
            },
        )
        put("format", visual.format)
        put("data", Base64.getEncoder().encodeToString(visual.jpegBytes))
    }
}

private fun rosbridgeStringPublish(topic: String, payload: JsonObject): JsonObject =
    rosbridgeMessagePublish(topic, buildJsonObject { put("data", payload.toString()) })

private fun rosbridgeMessagePublish(topic: String, message: JsonObject) = buildJsonObject {
    put("op", "publish")
    put("topic", topic)
    put("msg", message)
}

private fun Any?.toJsonElement(): JsonElement = when (this) {
    null -> JsonNull
    is Boolean -> JsonPrimitive(this)
    is Number -> JsonPrimitive(this)
    else -> JsonPrimitive(toString())
}
