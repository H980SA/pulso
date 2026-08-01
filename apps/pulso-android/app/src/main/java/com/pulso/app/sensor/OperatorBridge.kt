package com.pulso.app.sensor

import com.pulso.app.runtime.BrainTelemetryRecord
import com.pulso.app.runtime.GemmaTurnInput
import com.pulso.app.tools.ActionIntent
import com.pulso.app.tools.ActionResult
import java.util.Base64
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

internal data class OperatorCommand(
    val command: String,
    val nonce: String,
    val issuedAtEpochMs: Long,
)

/**
 * Telemetry flows from the phone to Mission Control. The only inbound surface
 * is a narrow, fresh, nonce-protected operator command topic. Failure leaves
 * the local brain running but motion remains bounded by its gateway lease.
 */
internal class OperatorBridge(private val websocketUrl: String) : AutoCloseable {
    private val json = Json { ignoreUnknownKeys = true }
    private val _commands = MutableSharedFlow<OperatorCommand>(extraBufferCapacity = 8)
    val commands: SharedFlow<OperatorCommand> = _commands.asSharedFlow()
    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(3, TimeUnit.SECONDS)
        .build()
    private val connected = CompletableDeferred<Unit>()
    private var socket: WebSocket? = null
    private var lastImagePublishedNs = Long.MIN_VALUE
    private var lastMetaPublishedNs = Long.MIN_VALUE
    private var lastTelemetryPublishedNs = Long.MIN_VALUE
    private var lastCameraInfoPublishedNs = Long.MIN_VALUE
    private var lastNavigationPublishedNs = Long.MIN_VALUE
    private var lastNavigationRevision = Long.MIN_VALUE
    private var lastNavigationCandidateSignature = ""
    @Volatile private var lastCommandNonce = ""
    private val telemetry = HilTelemetryPublisher { socket }

    suspend fun start(): Result<Unit> = runCatching {
        if (socket == null) {
            socket = client.newWebSocket(Request.Builder().url(websocketUrl).build(), Listener())
        }
        withTimeout(3_500) { connected.await() }
    }

    fun publishFrame(frame: SensorFrame): Boolean {
        val activeSocket = socket ?: return false
        var accepted = activeSocket.send(
            publishString("/pulso/hil/observation", observationPayload(frame)).toString()
        )
        frame.navigation?.takeIf {
            it.navigationRevision != lastNavigationRevision ||
                navigationCandidateSignature(it) != lastNavigationCandidateSignature ||
                shouldPublish(it.capturedMonotonicNs, lastNavigationPublishedNs, NAVIGATION_PERIOD_NS)
        }?.let { navigation ->
            accepted = activeSocket.send(
                publishString("/pulso/navigation/candidates", navigationPayload(navigation)).toString()
            ) && accepted
            lastNavigationRevision = navigation.navigationRevision
            lastNavigationCandidateSignature = navigationCandidateSignature(navigation)
            lastNavigationPublishedNs = navigation.capturedMonotonicNs
        }
        if (shouldPublish(frame.envelope.capturedMonotonicNs, lastTelemetryPublishedNs, TELEMETRY_PERIOD_NS)) {
            phoneTelemetryPayload(frame)?.let { payload ->
                accepted = activeSocket.send(
                    publishString("/pulso/phone/telemetry", payload).toString()
                ) && accepted
                lastTelemetryPublishedNs = frame.envelope.capturedMonotonicNs
            }
        }
        if (shouldPublish(frame.envelope.capturedMonotonicNs, lastCameraInfoPublishedNs, CAMERA_INFO_PERIOD_NS)) {
            cameraInfoPayload(frame)?.let { payload ->
                accepted = activeSocket.send(
                    publishString("/pulso/phone/rgb/camera_info", payload).toString()
                ) && accepted
                lastCameraInfoPublishedNs = frame.envelope.capturedMonotonicNs
            }
        }
        if (shouldPublish(frame.envelope.capturedMonotonicNs, lastImagePublishedNs, IMAGE_PERIOD_NS)) {
            (frame.operatorRgbJpeg ?: frame.egoRgbJpeg)?.let { bytes ->
                accepted = activeSocket.send(
                    publishMessage(
                        "/pulso/phone/rgb/compressed",
                        compressedImage(frame.envelope.capturedMonotonicNs, frame.envelope.frameId, bytes),
                    ).toString()
                ) && accepted
                lastImagePublishedNs = frame.envelope.capturedMonotonicNs
            }
        }
        if (shouldPublish(frame.envelope.capturedMonotonicNs, lastMetaPublishedNs, META_PERIOD_NS)) {
            frame.metaViewJpeg?.let { bytes ->
                accepted = activeSocket.send(
                    publishMessage(
                        "/pulso/navigation/metaview/compressed",
                        compressedImage(frame.envelope.capturedMonotonicNs, "map", bytes),
                    ).toString()
                ) && accepted
                lastMetaPublishedNs = frame.envelope.capturedMonotonicNs
            }
        }
        return accepted
    }

    fun publishMetaviewScene(jsonPayload: String): Boolean = socket?.send(
        publishString("/pulso/navigation/metaview_scene", jsonPayload).toString()
    ) ?: false

    fun publishAction(intent: ActionIntent, result: ActionResult): Boolean {
        val payload = buildJsonObject {
            put("contract_version", "pulso.action-result.v1")
            put("action_id", "PHONE-${System.nanoTime()}")
            put("captured_monotonic_ns", System.nanoTime())
            put("accepted", result.accepted)
            put("status", result.status)
            put("detail", result.detail)
            put("action_kind", intent.kind.name)
            put(
                "data",
                JsonObject(
                    (result.data + mapOf(
                        "target_id" to intent.target?.value,
                        "target_type" to intent.target?.kind?.name,
                    )).mapValues { (_, value) -> value.toJsonElement() }
                ),
            )
        }
        return socket?.send(publishString("/pulso/hil/action_result", payload).toString()) ?: false
    }

    fun publishBrainTrace(record: BrainTelemetryRecord): Boolean = telemetry.publishBrainTrace(record)

    fun publishGemmaInput(input: GemmaTurnInput): Boolean = telemetry.publishGemmaInput(input)

    fun publishPerceptionTracks(capturedNs: Long, tracks: List<PerceptionTrackObservation>): Boolean =
        telemetry.publishPerceptionTracks(capturedNs, tracks)

    fun publishPerceptionTelemetry(
        capturedNs: Long,
        modelId: String,
        status: String,
        count: Int,
        latencyMs: Long,
        semanticRevision: Long,
    ): Boolean = telemetry.publishPerceptionTelemetry(
        capturedNs,
        modelId,
        status,
        count,
        latencyMs,
        semanticRevision,
    )

    override fun close() {
        socket?.close(1000, "Operator bridge closed")
        socket = null
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            webSocket.send(
                buildJsonObject {
                    put("op", "subscribe")
                    put("id", "pulso-s25:operator-command")
                    put("topic", OPERATOR_COMMAND_TOPIC)
                    put("type", "std_msgs/String")
                    put("queue_length", 1)
                }.toString()
            )
            if (!connected.isCompleted) connected.complete(Unit)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val command = runCatching { parseOperatorCommand(text) }.getOrNull() ?: return
            if (command.nonce == lastCommandNonce) return
            if (kotlin.math.abs(System.currentTimeMillis() - command.issuedAtEpochMs) > COMMAND_MAX_AGE_MS) return
            lastCommandNonce = command.nonce
            _commands.tryEmit(command)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (!connected.isCompleted) connected.completeExceptionally(t)
            socket = null
        }
    }

    private companion object {
        const val IMAGE_PERIOD_NS = 100_000_000L
        const val META_PERIOD_NS = 500_000_000L
        const val TELEMETRY_PERIOD_NS = 500_000_000L
        const val CAMERA_INFO_PERIOD_NS = 2_000_000_000L
        const val NAVIGATION_PERIOD_NS = 1_000_000_000L
        const val OPERATOR_COMMAND_TOPIC = "/pulso/operator/command"
        const val COMMAND_MAX_AGE_MS = 10_000L
    }

    private fun parseOperatorCommand(raw: String): OperatorCommand? {
        val frame = json.parseToJsonElement(raw).jsonObject
        if (frame["op"]?.jsonPrimitive?.content != "publish") return null
        if (frame["topic"]?.jsonPrimitive?.content != OPERATOR_COMMAND_TOPIC) return null
        val data = frame["msg"]?.jsonObject?.get("data")?.jsonPrimitive?.content ?: return null
        val payload = json.parseToJsonElement(data).jsonObject
        val command = payload["command"]?.jsonPrimitive?.content ?: return null
        if (command !in setOf("ARM_ROVER", "START_AUTONOMY", "PAUSE_AUTONOMY", "STOP_ALL")) return null
        return OperatorCommand(
            command = command,
            nonce = payload["nonce"]?.jsonPrimitive?.content ?: return null,
            issuedAtEpochMs = payload["issued_at_ms"]?.jsonPrimitive?.longOrNull ?: return null,
        )
    }
}

private fun shouldPublish(capturedNs: Long, lastPublishedNs: Long, periodNs: Long): Boolean =
    lastPublishedNs == Long.MIN_VALUE || capturedNs < lastPublishedNs || capturedNs - lastPublishedNs >= periodNs

internal fun observationPayload(frame: SensorFrame): JsonObject = buildJsonObject {
    val envelope = frame.envelope
    val robot = frame.robot
    put("contract_version", envelope.contractVersion)
    put("observation_id", envelope.observationId)
    put("source", envelope.source.name)
    put("captured_monotonic_ns", envelope.capturedMonotonicNs)
    put("frame_id", envelope.frameId)
    put("tracking", buildJsonObject {
        put("state", envelope.trackingState)
        put("quality", envelope.trackingQuality)
        put("epoch", envelope.trackingEpoch)
    })
    put("robot", buildJsonObject {
        put("pose", buildJsonObject {
            put("position_m", JsonArray(listOf(robot.x, robot.y, 0f).map(::JsonPrimitive)))
            put("heading_deg", robot.headingDeg)
            put("confidence", robot.poseConfidence)
        })
        put("motion_state", robot.motionState)
        put("battery_fraction", robot.batteryFraction)
        put("flashlight_on", robot.flashlightOn)
        put("front_range_m", robot.frontRangeM?.let(::JsonPrimitive) ?: JsonNull)
    })
}

internal fun phoneTelemetryPayload(frame: SensorFrame): JsonObject? {
    val telemetry = frame.phoneTelemetry ?: return null
    return buildJsonObject {
        put("contract_version", "pulso.phone-telemetry.v1")
        put("captured_monotonic_ns", frame.envelope.capturedMonotonicNs)
        put("source", frame.envelope.source.name)
        put("frame_id", "phone_device")
        put("imu", buildJsonObject {
            put(
                "captured_monotonic_ns",
                telemetry.imuCapturedMonotonicNs?.let(::JsonPrimitive) ?: JsonNull,
            )
            put("acceleration_mps2", vector3Json(telemetry.accelerationMps2))
            put("angular_velocity_radps", vector3Json(telemetry.angularVelocityRadps))
        })
        put("battery", buildJsonObject {
            put("fraction", frame.robot.batteryFraction)
            put("temperature_c", telemetry.batteryTemperatureC?.let(::JsonPrimitive) ?: JsonNull)
        })
    }
}

internal fun cameraInfoPayload(frame: SensorFrame): JsonObject? {
    if (frame.envelope.source != SensorMode.ANDROID_REAL) return null
    val calibration = frame.cameraCalibration ?: return null
    return buildJsonObject {
        put("contract_version", "pulso.phone-camera-info.v1")
        put("captured_monotonic_ns", frame.envelope.capturedMonotonicNs)
        put("frame_id", "phone_rgb_optical_frame")
        put("calibration_source", "arcore/image_intrinsics")
        put("width", calibration.width)
        put("height", calibration.height)
        put("model", "pinhole")
        put("distortion_model", "not_reported")
        put("k", JsonArray(listOf(
            calibration.fx, 0f, calibration.cx,
            0f, calibration.fy, calibration.cy,
            0f, 0f, 1f,
        ).map(::JsonPrimitive)))
    }
}

private fun vector3Json(values: List<Float>?): JsonElement =
    if (values != null && values.size == 3 && values.all(Float::isFinite)) {
        JsonArray(values.map(::JsonPrimitive))
    } else {
        JsonNull
    }

private fun navigationCandidateSignature(navigation: NavigationObservation): String = navigation.candidates
    .sortedWith(compareBy({ it.type }, { it.id }))
    .joinToString("|") { "${it.type}:${it.id}:${it.targetRevision ?: "-"}:${it.capability}" }

internal fun navigationPayload(navigation: NavigationObservation): JsonObject = buildJsonObject {
    put("contract_version", "pulso.navigation.candidates.v1")
    put("captured_monotonic_ns", navigation.capturedMonotonicNs)
    put("sensor_map_seq", navigation.sensorMapSeq)
    put("navigation_revision", navigation.navigationRevision)
    put("valid_until_monotonic_ns", navigation.validUntilMonotonicNs)
    put("candidates", JsonArray(navigation.candidates.map { candidate ->
        buildJsonObject {
            put("type", candidate.type)
            put("id", candidate.id)
            put("label", candidate.label)
            put("purpose", candidate.purpose)
            put("position_m", JsonArray(listOf(candidate.x, candidate.y, 0f).map(::JsonPrimitive)))
            put("path_length_m", candidate.pathLengthM)
            put("risk", candidate.risk)
            put("information_gain", candidate.informationGain)
            put("capability", candidate.capability)
            candidate.targetRevision?.let { put("target_revision", it) }
        }
    }))
}

private fun compressedImage(capturedNs: Long, frameId: String, bytes: ByteArray): JsonObject =
    buildJsonObject {
        put("header", buildJsonObject {
            put("stamp", buildJsonObject {
                put("sec", capturedNs / 1_000_000_000L)
                put("nanosec", capturedNs % 1_000_000_000L)
            })
            put("frame_id", frameId)
        })
        put("format", "jpeg")
        put("data", Base64.getEncoder().encodeToString(bytes))
    }

private fun publishString(topic: String, payload: JsonObject): JsonObject =
    publishMessage(topic, buildJsonObject { put("data", payload.toString()) })

private fun publishString(topic: String, payload: String): JsonObject =
    publishMessage(topic, buildJsonObject { put("data", payload) })

private fun publishMessage(topic: String, message: JsonObject): JsonObject = buildJsonObject {
    put("op", "publish")
    put("topic", topic)
    put("msg", message)
}

private fun Any?.toJsonElement(): JsonElement = when (this) {
    null -> JsonNull
    is Boolean -> JsonPrimitive(this)
    is Number -> JsonPrimitive(this)
    is String -> JsonPrimitive(this)
    is Iterable<*> -> JsonArray(map { it.toJsonElement() })
    else -> JsonPrimitive(toString())
}
