package com.pulso.app.robot

import com.pulso.app.tools.ActionResult
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Typed HTTP client for the guarded ExoMy gateway. Each live call is one local timed pulse. */
class ExomyGatewayClient(
    private val baseUrl: String,
    private val token: String,
    override val dryRun: Boolean = true,
    private val http: OkHttpClient = defaultHttpClient(),
) : RoverMotorClient {
    private val json = Json { ignoreUnknownKeys = true }
    @Volatile private var connected = false
    @Volatile private var armed = false
    @Volatile private var leaseId: String? = null
    @Volatile private var worldRevision: Int? = null
    @Volatile private var stage = "UNKNOWN"
    @Volatile private var lastStatus = "DISCONNECTED"

    init {
        require(baseUrl.startsWith("http://") || baseUrl.startsWith("https://"))
    }

    override suspend fun connect(): ActionResult = withContext(Dispatchers.IO) {
        if (token.isBlank()) {
            return@withContext result(false, "PAIRING_REQUIRED", "The field APK has no provisioned rover credential.")
        }
        runCatching {
            executeJson("GET", "/health", authenticated = false)
            refreshWorldState()
        }.fold(
            onSuccess = {
                connected = true
                armed = false
                lastStatus = "CONNECTED_$stage"
                result(true, "CONNECTED", "ExoMy gateway connected in $stage; motors remain disarmed.")
            },
            onFailure = {
                connected = false
                armed = false
                lastStatus = "CONNECT_FAILED"
                result(false, "CONNECT_FAILED", it.safeMessage())
            },
        )
    }

    override suspend fun arm(operatorPresent: Boolean): ActionResult = withContext(Dispatchers.IO) {
        if (!connected) return@withContext result(false, "DISCONNECTED", "Connect the rover gateway first.")
        if (!dryRun && !operatorPresent) {
            return@withContext result(false, "OPERATOR_REQUIRED", "Live control requires an operator at the power cutoff.")
        }
        runCatching {
            var world = refreshWorldState()
            val estopLatched = world["safety"]?.jsonObject
                ?.get("estop_latched")?.jsonPrimitive?.content == "true"
            if (estopLatched) {
                executeJson(
                    method = "POST",
                    path = "/v1/estop/reset",
                    body = buildJsonObject { put("reason", "Explicit Mission Control HABILITAR ROVER") },
                )
                world = refreshWorldState()
            }
            if (!dryRun) validateGroundAdmission(world)
            val response = executeJson(
                method = "POST",
                path = "/v1/control-leases",
                body = buildJsonObject {
                    put("holder", HOLDER)
                    put("ttl_seconds", LEASE_TTL_SECONDS)
                },
            )
            leaseId = response.body.requiredString("lease_id")
            response.revision?.let { worldRevision = it }
            if (response.revision == null) refreshWorldState()
            armed = true
            lastStatus = if (dryRun) "ARMED_SHADOW" else "ARMED_GROUND_SUPERVISED"
            result(true, lastStatus, "Exclusive ${LEASE_TTL_SECONDS}s lease acquired; every motion is limited to one ${GROUND_PULSE_MS}ms CREEP pulse.")
        }.getOrElse {
            armed = false
            leaseId = null
            lastStatus = "ARM_FAILED"
            result(false, "ARM_FAILED", it.safeMessage())
        }
    }

    override suspend fun disarm(reason: String): ActionResult = withContext(Dispatchers.IO) {
        val stop = runCatching { sendCommand(ZeusCommand.Stop, reason) }.getOrNull()
        val lease = leaseId
        if (lease != null) {
            runCatching { executeJson("DELETE", "/v1/control-leases/$lease") }
        }
        leaseId = null
        armed = false
        lastStatus = "DISARMED"
        result(
            accepted = stop?.accepted == true,
            status = "DISARMED",
            detail = "Lease released; gateway STOP ${if (stop?.accepted == true) "completed" else "could not be confirmed"}.",
        )
    }

    override suspend fun command(command: ZeusCommand): ActionResult = withContext(Dispatchers.IO) {
        if (command != ZeusCommand.Stop && (!connected || !armed || leaseId == null)) {
            return@withContext result(false, "NOT_ARMED", "An explicit fresh control lease is required.")
        }
        runCatching { sendCommand(command, "Pulso closed-loop action") }.getOrElse {
            armed = false
            leaseId = null
            lastStatus = "COMMAND_FAILED"
            result(false, "COMMAND_FAILED", it.safeMessage())
        }
    }

    override fun safetyStatus(): Map<String, Any> = mapOf(
        "gateway_url" to baseUrl,
        "connected" to connected,
        "armed" to armed,
        "dry_run" to dryRun,
        "stage" to stage,
        "pulse_ms" to GROUND_PULSE_MS,
        "lease_ttl_seconds" to LEASE_TTL_SECONDS,
        "credential_provisioned" to token.isNotBlank(),
        "safety_status" to lastStatus,
    )

    override fun close() {
        armed = false
        leaseId = null
        connected = false
        http.dispatcher.executorService.shutdown()
        http.connectionPool.evictAll()
    }

    private fun validateGroundAdmission(world: JsonObject) {
        val reportedStage = world.requiredString("stage")
        val safety = world["safety"]?.jsonObject ?: error("Gateway omitted safety state")
        check(reportedStage == "GROUND") { "Gateway is $reportedStage; live phone control requires GROUND." }
        check(safety["allow_actuation"]?.jsonPrimitive?.content == "true") { "Gateway actuation is disabled." }
        check((safety["max_duration_ms"]?.jsonPrimitive?.intOrNull ?: Int.MAX_VALUE) <= MAX_GROUND_DURATION_MS) {
            "Gateway ground pulse limit is too permissive."
        }
    }

    private fun sendCommand(command: ZeusCommand, reason: String): ActionResult {
        if (worldRevision == null) refreshWorldState()
        val revision = worldRevision ?: error("No fresh gateway world revision")
        val payload = commandPayload(command, revision, reason)
        val response = executeJson(
            method = "POST",
            path = "/v1/commands",
            body = payload,
            idempotencyKey = UUID.randomUUID().toString(),
        )
        response.revision?.let { worldRevision = it }
        if (response.revision == null) refreshWorldState()
        val status = response.body.requiredString("status")
        val dispatched = response.body["dispatched_to_ros"]?.jsonPrimitive?.content == "true"
        val accepted = status in setOf("SUCCEEDED", "SHADOWED")
        lastStatus = status
        val physical = response.body["physical_achievement"]?.jsonPrimitive?.contentOrNull ?: "UNVERIFIED"
        return result(
            accepted,
            status,
            if (command == ZeusCommand.Stop) {
                "Gateway completed STOP; physical achievement remains $physical."
            } else {
                "One bounded pulse completed; ROS dispatch=$dispatched and physical achievement=$physical."
            },
        )
    }

    private fun commandPayload(command: ZeusCommand, revision: Int, reason: String): JsonObject = buildJsonObject {
        put("expected_world_revision", revision)
        put("speed_profile", "CREEP")
        put("reason", reason)
        put("requested_by", HOLDER)
        when (command) {
            ZeusCommand.Stop -> put("command_type", "STOP")
            is ZeusCommand.Drive -> {
                leaseId?.let { put("lease_id", it) }
                put("duration_ms", GROUND_PULSE_MS)
                if (command.power <= 0) {
                    put("command_type", "TURN_TIMED")
                    put("direction", if (command.headingCorrectionDeg >= 0f) "LEFT" else "RIGHT")
                } else {
                    put("command_type", "DRIVE_TIMED")
                    put("direction", "FORWARD")
                }
            }
        }
    }

    private fun refreshWorldState(): JsonObject {
        val response = executeJson("GET", "/v1/world-state")
        stage = response.body.requiredString("stage")
        worldRevision = response.body["world_revision"]?.jsonPrimitive?.intOrNull
            ?: error("Gateway omitted world_revision")
        return response.body
    }

    private fun executeJson(
        method: String,
        path: String,
        body: JsonObject? = null,
        authenticated: Boolean = true,
        idempotencyKey: String? = null,
    ): GatewayResponse {
        val requestBody = body?.toString()?.toRequestBody(JSON_MEDIA_TYPE)
        val builder = Request.Builder().url(baseUrl.trimEnd('/') + path)
        if (authenticated) builder.header("Authorization", "Bearer $token")
        if (idempotencyKey != null) builder.header("Idempotency-Key", idempotencyKey)
        when (method) {
            "GET" -> builder.get()
            "POST" -> builder.post(requestBody ?: EMPTY_BODY)
            "DELETE" -> builder.delete(requestBody)
            else -> error("Unsupported HTTP method $method")
        }
        http.newCall(builder.build()).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val detail = runCatching {
                    json.parseToJsonElement(text).jsonObject["detail"]?.jsonPrimitive?.content
                }.getOrNull()
                throw IOException("Gateway HTTP ${response.code}: ${detail ?: "request rejected"}")
            }
            val parsed = if (text.isBlank()) buildJsonObject { } else json.parseToJsonElement(text).jsonObject
            return GatewayResponse(parsed, response.header(REVISION_HEADER)?.toIntOrNull())
        }
    }

    private fun result(accepted: Boolean, status: String, detail: String) = ActionResult(
        accepted = accepted,
        status = status,
        detail = detail,
        data = safetyStatus(),
    )

    private fun JsonObject.requiredString(key: String): String =
        this[key]?.jsonPrimitive?.contentOrNull ?: error("Gateway omitted $key")

    private fun Throwable.safeMessage(): String = message ?: this::class.java.simpleName

    private data class GatewayResponse(val body: JsonObject, val revision: Int?)

    companion object {
        const val GROUND_PULSE_MS = 100
        const val MAX_GROUND_DURATION_MS = 150
        const val LEASE_TTL_SECONDS = 30
        const val REVISION_HEADER = "X-Pulso-World-Revision"
        private const val HOLDER = "pulso-s25"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val EMPTY_BODY = ByteArray(0).toRequestBody(null)

        private fun defaultHttpClient() = OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(4, TimeUnit.SECONDS)
            .writeTimeout(2, TimeUnit.SECONDS)
            .build()
    }
}
