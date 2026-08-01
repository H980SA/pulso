package com.pulso.app.sensor

import com.pulso.app.runtime.GemmaTurnInput
import com.pulso.app.runtime.GemmaVisualInput
import com.pulso.app.runtime.runAfterGemmaInputPublished
import java.util.Base64
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.Request
import okhttp3.WebSocket
import okio.ByteString
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GemmaInputTelemetryTest {
    @Test
    fun jsonContainsTheExactInitialTurnTextAndVisualMetadata() {
        val input = inputWithVisual()

        val payload = gemmaInputPayload(input, publishedMonotonicNs = 7_000_000_042L)
        val image = payload.getValue("image").jsonObject

        assertEquals(
            setOf(
                "contract_version",
                "input_id",
                "published_monotonic_ns",
                "turn_id",
                "selected_world_seq",
                "model_id",
                "input_kind",
                "exact_message",
                "prompt_text",
                "image",
                "system_prompt",
                "system_prompt_sha256",
                "tool_schemas",
                "tool_schemas_sha256",
                "conversation_scope",
                "conversation_reused_within_turn",
                "conversation_reused_across_turns",
            ),
            payload.keys,
        )
        assertEquals("TURN-22", payload.getValue("turn_id").jsonPrimitive.content)
        assertEquals(22L, payload.getValue("selected_world_seq").jsonPrimitive.content.toLong())
        assertEquals(input.promptText, payload.getValue("prompt_text").jsonPrimitive.content)
        assertEquals(input.systemPrompt, payload.getValue("system_prompt").jsonPrimitive.content)
        assertEquals(input.systemPromptSha256, payload.getValue("system_prompt_sha256").jsonPrimitive.content)
        assertEquals(input.image?.jpegSha256, image.getValue("jpeg_sha256").jsonPrimitive.content)
        assertEquals(input.image?.byteLength, image.getValue("byte_length").jsonPrimitive.content.toInt())
        assertFalse(payload.toString().contains("chain_of_thought"))
    }

    @Test
    fun compressedViewRoundTripsTheSameBytesWithoutReencoding() {
        val input = inputWithVisual()

        val message = requireNotNull(gemmaViewMessage(input, 7_000_000_042L))
        val decoded = Base64.getDecoder().decode(message.getValue("data").jsonPrimitive.content)

        assertArrayEquals(input.image?.jpegBytes, decoded)
        assertEquals("jpeg", message.getValue("format").jsonPrimitive.content)
    }

    @Test
    fun textOnlyTurnPublishesNoImageMessage() {
        val input = inputWithVisual().copy(image = null)
        val payload = gemmaInputPayload(input, 99)

        assertNull(gemmaViewMessage(input, 99))
        assertEquals("null", payload.getValue("image").toString())
    }

    @Test
    fun publishesInputThenImageBeforeInference() = runTest {
        val order = mutableListOf<String>()
        val socket = RecordingWebSocket(order)
        val publisher = HilTelemetryPublisher { socket }
        val input = inputWithVisual()

        runAfterGemmaInputPublished(
            input = input,
            publishInput = { publisher.publishGemmaInput(it) },
            inference = { order += "inference" },
        )

        assertEquals(
            listOf(
                "/pulso/hil/gemma_input",
                "/pulso/hil/gemma_view/compressed",
                "inference",
            ),
            order,
        )
    }

    private fun inputWithVisual(): GemmaTurnInput {
        val bytes = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 4, 5, 0xff.toByte(), 0xd9.toByte())
        return GemmaTurnInput(
            inputId = "IN-TURN-22",
            turnId = "TURN-22",
            selectedWorldSeq = 22,
            modelId = "gemma-4-e4b-it-litertlm",
            inputKind = "WORLD_PACKET",
            exactMessage = buildJsonObject {
                put("role", "user")
                put("parts", buildJsonArray {
                    add(buildJsonObject { put("kind", "text") })
                    add(buildJsonObject { put("kind", "inline_data") })
                })
            },
            promptText = "CURRENT WORLD PACKET\nexact prompt",
            image = GemmaVisualInput(
                artifactId = "META-22",
                kind = "META_VIEW",
                sourceTopic = "/pulso/navigation/metaview/compressed",
                capturedMonotonicNs = 4_000_000_000L,
                format = "jpeg",
                jpegSha256 = "9b2c9d7d38f39f6b2d20fe9ed8ae18aa7e30122ccbf5863fd73a985202a72f6b",
                byteLength = bytes.size,
                auditTopic = "/pulso/hil/gemma_view/compressed",
                jpegBytes = bytes,
            ),
            systemPrompt = "system",
            systemPromptSha256 = "9b2c9d7d38f39f6b2d20fe9ed8ae18aa7e30122ccbf5863fd73a985202a72f6b",
            toolSchemas = buildJsonArray { add(buildJsonObject { put("name", "move_to") }) },
            toolSchemasSha256 = "9b2c9d7d38f39f6b2d20fe9ed8ae18aa7e30122ccbf5863fd73a985202a72f6b",
        )
    }

    private class RecordingWebSocket(
        private val order: MutableList<String>,
    ) : WebSocket {
        override fun request(): Request = Request.Builder().url("ws://localhost:9091").build()
        override fun queueSize(): Long = 0
        override fun send(text: String): Boolean {
            val topic = Json.parseToJsonElement(text).jsonObject
                .getValue("topic").jsonPrimitive.content
            order += topic
            return true
        }
        override fun send(bytes: ByteString): Boolean = true
        override fun close(code: Int, reason: String?): Boolean = true
        override fun cancel() = Unit
    }
}
