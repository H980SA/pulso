package com.pulso.app.runtime

import android.content.Context
import android.os.SystemClock
import java.io.File
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Append-only local evidence journal. It records observable harness inputs and
 * outputs, never hidden model reasoning. The web console may mirror the same
 * records into SQLite, but the phone remains independently auditable offline.
 */
class MissionEventJournal(context: Context) {
    private val sessionId = "S-${SESSION_FORMAT.format(Instant.now())}"
    private val sessionDir = File(context.getExternalFilesDir(null) ?: context.filesDir, "sessions/$sessionId")
        .apply { mkdirs() }
    private val artifactDir = File(sessionDir, "artifacts").apply { mkdirs() }
    private val eventsFile = File(sessionDir, "events.jsonl")

    fun id(): String = sessionId

    @Synchronized
    fun append(category: String, summary: String, payload: Map<String, Any?> = emptyMap()) {
        val record = JsonObject(
            linkedMapOf(
                "schema" to JsonPrimitive("pulso.journal.event.v1"),
                "session_id" to JsonPrimitive(sessionId),
                "wall_time" to JsonPrimitive(Instant.now().toString()),
                "monotonic_ms" to JsonPrimitive(SystemClock.elapsedRealtime()),
                "category" to JsonPrimitive(category),
                "summary" to JsonPrimitive(summary),
                "payload" to payload.toJsonObject(),
            )
        )
        eventsFile.appendText(record.toString() + "\n", Charsets.UTF_8)
    }

    @Synchronized
    fun recordGemmaInput(input: GemmaTurnInput) {
        append(
            category = "GEMMA_INPUT",
            summary = "${input.inputKind} ${input.inputId}",
            payload = mapOf(
                "input_id" to input.inputId,
                "turn_id" to input.turnId,
                "world_seq" to input.selectedWorldSeq,
                "model_id" to input.modelId,
                "input_kind" to input.inputKind,
                "exact_message" to input.exactMessage,
                "system_prompt" to input.systemPrompt,
                "system_prompt_sha256" to input.systemPromptSha256,
                "tool_schemas" to input.toolSchemas,
                "tool_schemas_sha256" to input.toolSchemasSha256,
                "conversation_scope" to input.conversationScope,
            ),
        )
        input.image?.let { image ->
            persistArtifact(
                artifactId = image.artifactId,
                kind = image.kind,
                bytes = image.jpegBytes,
                extension = "jpg",
                metadata = mapOf(
                    "turn_id" to input.turnId,
                    "capture_ns" to image.capturedMonotonicNs,
                    "source_topic" to image.sourceTopic,
                    "declared_sha256" to image.jpegSha256,
                ),
            )
        }
    }

    @Synchronized
    fun persistArtifact(
        artifactId: String,
        kind: String,
        bytes: ByteArray,
        extension: String,
        metadata: Map<String, Any?> = emptyMap(),
    ): String {
        val digest = sha256Hex(bytes)
        val safeId = artifactId.replace(Regex("[^A-Za-z0-9._-]"), "_").take(96)
        val filename = "${safeId.ifBlank { digest.take(16) }}-${digest.take(12)}.$extension"
        val artifact = File(artifactDir, filename)
        if (!artifact.exists()) artifact.writeBytes(bytes)
        append(
            category = "ARTIFACT",
            summary = "$kind $artifactId",
            payload = metadata + mapOf(
                "artifact_id" to artifactId,
                "kind" to kind,
                "sha256" to digest,
                "byte_length" to bytes.size,
                "relative_path" to "artifacts/$filename",
            ),
        )
        return artifact.absolutePath
    }

    private companion object {
        val SESSION_FORMAT: DateTimeFormatter = DateTimeFormatter
            .ofPattern("yyyyMMdd-HHmmss")
            .withZone(ZoneOffset.UTC)
    }
}

private fun Map<String, Any?>.toJsonObject(): JsonObject = JsonObject(
    entries.associate { (key, value) -> key to value.toJsonElement() }
)

private fun Any?.toJsonElement(): JsonElement = when (this) {
    null -> JsonNull
    is JsonElement -> this
    is Boolean -> JsonPrimitive(this)
    is Number -> JsonPrimitive(this)
    is String -> JsonPrimitive(this)
    is Map<*, *> -> JsonObject(entries.associate { (key, value) -> key.toString() to value.toJsonElement() })
    is Iterable<*> -> JsonArray(map { it.toJsonElement() })
    is Array<*> -> JsonArray(map { it.toJsonElement() })
    else -> JsonPrimitive(toString())
}
