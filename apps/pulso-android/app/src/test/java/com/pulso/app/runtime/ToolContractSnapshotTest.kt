package com.pulso.app.runtime

import com.google.adk.kt.types.FunctionDeclaration
import com.google.adk.kt.types.Schema
import com.google.adk.kt.types.Type
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ToolContractSnapshotTest {
    @Test
    fun serializesAndHashesTheAdkFunctionDeclarationValue() {
        val declaration = FunctionDeclaration(
            name = "move_to",
            description = "Navigate to one candidate.",
            parameters = Schema(
                type = Type.OBJECT,
                properties = mapOf(
                    "target_id" to Schema(type = Type.STRING, description = "Current ID"),
                ),
                required = listOf("target_id"),
            ),
        )

        val snapshot = captureToolContracts(listOf(declaration))
        val rendered = snapshot.schemas.single().toString()

        assertTrue(rendered.contains("\"name\":\"move_to\""))
        assertTrue(rendered.contains("\"target_id\""))
        assertEquals(
            sha256Hex(snapshot.schemas.toString().toByteArray(Charsets.UTF_8)),
            snapshot.sha256,
        )
    }
}
