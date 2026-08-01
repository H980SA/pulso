package com.pulso.app.runtime

import com.google.adk.kt.types.FunctionDeclaration
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray

private val toolContractJson = Json {
    encodeDefaults = false
    explicitNulls = false
}

/** Serializes the same FunctionDeclaration values exposed by the ADK tools. */
internal fun captureToolContracts(
    declarations: List<FunctionDeclaration>,
): ToolContractSnapshot {
    val schemas = JsonArray(
        declarations.map { declaration ->
            toolContractJson.encodeToJsonElement(
                FunctionDeclaration.serializer(),
                declaration,
            )
        }
    )
    return ToolContractSnapshot(
        schemas = schemas,
        sha256 = sha256Hex(schemas.toString().toByteArray(Charsets.UTF_8)),
    )
}
