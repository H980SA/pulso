package com.pulso.app.runtime

import com.pulso.app.context.ContextSelector
import com.pulso.app.demo.demoWorld
import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.VisualView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class GemmaTurnInputTest {
    private val cognitive = CognitiveState("question", "plan", null, null)
    private val checkpoint = MissionCheckpoint("M-001", "G-001", emptyList(), emptyList(), emptyList())

    @Test
    fun snapshotUsesTheExactPromptAndRequestedJpegPassedToAdk() {
        val world = demoWorld()
        val jpeg = byteArrayOf(0x01, 0x02, 0x03, 0x7f)
        val requested = VisualView(
            artifactId = "META-NAV-${world.navigationRevision}",
            kind = "META_VIEW",
            navigationRevision = world.navigationRevision,
            requestActionId = "A-REQUEST-1",
            capturedAtMonotonicMs = 4432,
            jpegBytes = jpeg,
        )
        val packet = ContextSelector().select(
            world,
            DecisionNeed.CHOOSE_ROUTE,
            cognitive,
            checkpoint,
            requested,
        )

        val snapshot = prepareGemmaTurnInput(
            packet,
            turnId = "TURN-17",
            systemPrompt = "system prompt",
            toolContracts = toolContracts(),
        )

        assertEquals(packet.toPrompt(), snapshot.promptText)
        assertEquals("gemma-4-e4b-it-litertlm", PULSO_GEMMA_MODEL_ID)
        assertEquals(PULSO_GEMMA_MODEL_ID, snapshot.modelId)
        assertSame(jpeg, snapshot.image?.jpegBytes)
        assertEquals(jpeg.size, snapshot.image?.byteLength)
        assertEquals(sha256Hex(jpeg), snapshot.image?.jpegSha256)
        assertEquals(sha256Hex("system prompt".toByteArray()), snapshot.systemPromptSha256)
        assertEquals(toolContracts().sha256, snapshot.toolSchemasSha256)
    }

    @Test
    fun textOnlyTurnHasNoVisualPayload() {
        val packet = ContextSelector().select(
            demoWorld(),
            DecisionNeed.MONITOR,
            cognitive,
            checkpoint,
        )

        val snapshot = prepareGemmaTurnInput(packet, "TURN-18", "system", toolContracts())

        assertNull(snapshot.image)
        assertTrue(requireNotNull(snapshot.promptText).contains("No visual view is attached"))
    }

    @Test
    fun runtimeRejectsAnUnauthorizedVisualEvenIfACallerBypassesTheSelector() {
        val clean = ContextSelector().select(
            demoWorld(),
            DecisionNeed.CHOOSE_ROUTE,
            cognitive,
            checkpoint,
        )
        val bypassed = clean.copy(
            visualView = VisualView(
                artifactId = "unrequested",
                kind = "META_VIEW",
                navigationRevision = clean.candidates.first().navigationRevision,
                jpegBytes = byteArrayOf(9),
            )
        )

        assertThrows(IllegalArgumentException::class.java) {
            prepareGemmaTurnInput(bypassed, "TURN-BYPASS", "system", toolContracts())
        }
    }

    @Test
    fun exactMessagePreservesTextThenImageOrder() {
        val world = demoWorld()
        val packet = ContextSelector().select(
            world,
            DecisionNeed.CHOOSE_ROUTE,
            cognitive,
            checkpoint,
            VisualView(
                artifactId = "META",
                kind = "META_VIEW",
                navigationRevision = world.navigationRevision,
                requestActionId = "A-1",
                jpegBytes = byteArrayOf(1),
            ),
        )

        val snapshot = prepareGemmaTurnInput(packet, "TURN-ORDER", "system", toolContracts())
        val rendered = snapshot.exactMessage.toString()

        assertTrue(rendered.indexOf("\"kind\":\"text\"") < rendered.indexOf("\"kind\":\"inline_data\""))
    }

    @Test
    fun toolResultSnapshotPreservesTheExactResponseForTheNextStep() {
        val initial = prepareGemmaTurnInput(
            ContextSelector().select(
                demoWorld(),
                DecisionNeed.MONITOR,
                cognitive,
                checkpoint,
            ),
            "TURN-TOOLS",
            "system",
            toolContracts(),
        )

        val toolInput = prepareGemmaToolResultInput(
            initialInput = initial,
            sequence = 1,
            responses = listOf(
                GemmaToolResponseInput(
                    "load_skill",
                    mapOf(
                        "accepted" to true,
                        "instructions" to "inspect breathing and entrapment",
                    ),
                )
            ),
        )

        assertEquals("TOOL_RESULT", toolInput.inputKind)
        assertNull(toolInput.promptText)
        assertNull(toolInput.image)
        assertTrue(toolInput.exactMessage.toString().contains("inspect breathing and entrapment"))
    }

    private fun toolContracts(): ToolContractSnapshot {
        val schemas = buildJsonArray {
            add(buildJsonObject { put("name", "move_to") })
        }
        return ToolContractSnapshot(schemas, sha256Hex(schemas.toString().toByteArray()))
    }
}
