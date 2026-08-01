package com.pulso.app.sensor

import android.util.Base64
import com.pulso.app.tools.ActionIntent
import com.pulso.app.tools.ActionResult
import com.pulso.app.runtime.BrainTelemetryRecord
import com.pulso.app.runtime.GemmaTurnInput
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.floatOrNull
import kotlinx.serialization.json.float
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class GazeboHilSource(
    private val websocketUrl: String,
) : PulsoSensorSource {
    override val mode = SensorMode.GAZEBO_HIL
    private val json = Json { ignoreUnknownKeys = true }
    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(4, TimeUnit.SECONDS)
        .build()
    private val _observations = MutableSharedFlow<SensorFrame>(
        replay = 1,
        extraBufferCapacity = 4,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    private val _actionEvents = MutableSharedFlow<ActionResult>(extraBufferCapacity = 16)
    private val pendingActions = ConcurrentHashMap<String, CompletableDeferred<ActionResult>>()
    private var socket: WebSocket? = null
    private var connected = CompletableDeferred<Unit>()
    private var latestEnvelope: ObservationEnvelope? = null
    private var latestRobot: RobotObservation? = null
    private var latestNavigation: NavigationObservation? = null
    private val viewBuffer = FreshViewBuffer()
    private var latestCameraCalibration: CameraCalibration? = null
    private val telemetryPublisher = HilTelemetryPublisher { socket }

    override val observations: Flow<SensorFrame> = _observations.asSharedFlow()
    val actionEvents: Flow<ActionResult> = _actionEvents.asSharedFlow()

    override suspend fun start() {
        if (socket != null) return
        connected = CompletableDeferred()
        socket = client.newWebSocket(Request.Builder().url(websocketUrl).build(), Listener())
        withTimeout(5_000) { connected.await() }
    }

    override suspend fun stop() {
        socket?.let { sendBestEffortStop(it, "source_stop") }
        socket?.close(1000, "Pulso HIL stopped")
        socket = null
        pendingActions.values.forEach { it.cancel() }
        pendingActions.clear()
    }

    suspend fun dispatch(intent: ActionIntent): ActionResult {
        val activeSocket = socket
            ?: return ActionResult(false, "HIL_DISCONNECTED", "Gazebo HIL is not connected.")
        val actionId = "A-${System.nanoTime()}"
        val deferred = CompletableDeferred<ActionResult>()
        val requestedViewKind = intent.parameters["view_kind"] as? String ?: "CANDIDATE_VIEW"
        val bufferedKind = if (requestedViewKind == "META_VIEW") "META_VIEW" else "EGO_RGB"
        val viewBaselineNs = viewBuffer.latest(bufferedKind)?.capturedMonotonicNs ?: -1L
        pendingActions[actionId] = deferred
        val targetJson = intent.target?.let { target ->
            buildJsonObject {
                put("type", target.kind.name)
                put("id", target.value)
            }
        }
        val action = buildJsonObject {
            put("contract_version", "pulso.action.v1")
            put("action_id", actionId)
            put("mission_id", "M-001")
            put("issued_monotonic_ns", System.nanoTime())
            put("kind", intent.kind.name)
            put("target", targetJson ?: JsonNull)
            intent.candidateCapability?.let { put("candidate_capability", it) }
            intent.expectedNavigationRevision?.let { put("expected_navigation_revision", it) }
            intent.expectedTrackingEpoch?.let { put("expected_tracking_epoch", it) }
            intent.expectedTargetRevision?.let { put("expected_target_revision", it) }
            put("parameters", JsonObject(intent.parameters.mapValues { it.value.toJsonElement() }))
        }
        val command = rosbridgePublish("/pulso/hil/action_intent", JsonPrimitive(action.toString()))
        if (!activeSocket.send(command.toString())) {
            pendingActions.remove(actionId)
            return ActionResult(false, "SEND_FAILED", "Rosbridge rejected the outgoing frame.")
        }
        val terminalTimeoutMs = when (intent.kind) {
            com.pulso.app.tools.ActionKind.MOVE_TO -> 65_000L
            com.pulso.app.tools.ActionKind.LOOK_AT -> 20_000L
            else -> 5_000L
        }
        val result = runCatching { withTimeout(terminalTimeoutMs) { deferred.await() } }
            .getOrElse {
                pendingActions.remove(actionId)
                if (intent.kind in HIL_MOTION_ACTIONS) sendBestEffortStop(activeSocket, "client_timeout")
                ActionResult(
                    false,
                    "ACTION_RESULT_TIMEOUT",
                    "No terminal action result arrived in ${terminalTimeoutMs}ms.",
                )
            }
        if (intent.kind != com.pulso.app.tools.ActionKind.REQUEST_VIEW || !result.accepted) {
            return result
        }
        val freshView = runCatching {
            viewBuffer.awaitAfter(bufferedKind, viewBaselineNs, 2_500)
        }.getOrElse {
            return ActionResult(false, "VIEW_CAPTURE_TIMEOUT", "No post-request camera frame arrived.")
        }
        return result.copy(
            detail = "Fresh $requestedViewKind captured after the request.",
            data = result.data + mapOf(
                "action_id" to actionId,
                "artifact_capture_ns" to freshView.capturedMonotonicNs,
            ),
        )
    }

    fun publishPerceptionTracks(
        capturedMonotonicNs: Long,
        tracks: List<PerceptionTrackObservation>,
    ): Boolean = telemetryPublisher.publishPerceptionTracks(capturedMonotonicNs, tracks)

    /** Best-effort, read-only operator evidence. Never blocks the agent loop. */
    internal fun publishBrainTrace(record: BrainTelemetryRecord): Boolean =
        telemetryPublisher.publishBrainTrace(record)

    /** Exact initial Gemma content; always called synchronously before ADK inference. */
    internal fun publishGemmaInput(input: GemmaTurnInput): Boolean =
        telemetryPublisher.publishGemmaInput(input)

    /** Detector health and timing, separated from semantic tracks and images. */
    fun publishPerceptionTelemetry(
        sourceCaptureNs: Long,
        modelId: String,
        status: String,
        detectionCount: Int,
        inferenceLatencyMs: Long,
        semanticRevision: Long,
    ): Boolean = telemetryPublisher.publishPerceptionTelemetry(
        sourceCaptureNs,
        modelId,
        status,
        detectionCount,
        inferenceLatencyMs,
        semanticRevision,
    )

    override fun close() {
        socket?.let { sendBestEffortStop(it, "source_close") }
        socket?.cancel()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            listOf(
                "/pulso/hil/observation" to "std_msgs/msg/String",
                "/pulso/navigation/candidates" to "std_msgs/msg/String",
                "/pulso/hil/action_result" to "std_msgs/msg/String",
                "/pulso/navigation/metaview/compressed" to "sensor_msgs/msg/CompressedImage",
                "/pulso/phone/rgb/compressed" to "sensor_msgs/msg/CompressedImage",
                "/pulso/phone/rgb/camera_info" to "sensor_msgs/msg/CameraInfo",
            ).forEach { (topic, type) -> webSocket.send(rosbridgeSubscribe(topic, type).toString()) }
            connected.complete(Unit)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val outer = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            if (outer["op"]?.jsonPrimitive?.contentOrNull != "publish") return
            val topic = outer["topic"]?.jsonPrimitive?.contentOrNull ?: return
            val message = outer["msg"]?.jsonObject ?: return
            when (topic) {
                "/pulso/hil/observation" -> message.stringData()?.let(::parseObservation)
                "/pulso/navigation/candidates" -> message.stringData()?.let(::parseNavigation)
                "/pulso/hil/action_result" -> message.stringData()?.let(::parseActionResult)
                "/pulso/navigation/metaview/compressed" -> {
                    message.decodedView()?.let { (capturedNs, jpeg) ->
                        viewBuffer.update("META_VIEW", capturedNs, jpeg)
                    }
                    emitFrame()
                }
                "/pulso/phone/rgb/compressed" -> {
                    message.decodedView()?.let { (capturedNs, jpeg) ->
                        viewBuffer.update("EGO_RGB", capturedNs, jpeg)
                    }
                    emitFrame()
                }
                "/pulso/phone/rgb/camera_info" -> parseCameraInfo(message)
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (!connected.isCompleted) connected.completeExceptionally(t)
            socket = null
            pendingActions.values.forEach { it.completeExceptionally(t) }
            pendingActions.clear()
        }
    }

    private fun parseObservation(payload: String) {
        val root = runCatching { json.parseToJsonElement(payload).jsonObject }.getOrNull() ?: return
        val tracking = root["tracking"]?.jsonObject ?: return
        val robotJson = root["robot"]?.jsonObject ?: return
        val pose = robotJson["pose"]?.jsonObject ?: return
        val position = pose["position_m"]?.jsonArray ?: return
        val artifacts = root["artifacts"]?.jsonArray.orEmpty().associate { artifactElement ->
            val artifact = artifactElement.jsonObject
            artifact["kind"]!!.jsonPrimitive.content to artifact["uri"]!!.jsonPrimitive.content
        }
        latestEnvelope = ObservationEnvelope(
            observationId = root["observation_id"]!!.jsonPrimitive.content,
            source = SensorMode.GAZEBO_HIL,
            capturedMonotonicNs = root["captured_monotonic_ns"]!!.jsonPrimitive.long,
            frameId = root["frame_id"]!!.jsonPrimitive.content,
            trackingState = tracking["state"]!!.jsonPrimitive.content,
            trackingQuality = tracking["quality"]!!.jsonPrimitive.float,
            trackingEpoch = tracking["epoch"]!!.jsonPrimitive.long,
            artifactUris = artifacts,
        )
        latestRobot = RobotObservation(
            x = position.floatAt(0),
            y = position.floatAt(1),
            headingDeg = pose["heading_deg"]!!.jsonPrimitive.float,
            poseConfidence = pose["confidence"]!!.jsonPrimitive.float,
            motionState = robotJson["motion_state"]!!.jsonPrimitive.content,
            batteryFraction = robotJson["battery_fraction"]!!.jsonPrimitive.float,
            flashlightOn = robotJson["flashlight_on"]!!.jsonPrimitive.boolean,
            frontRangeM = robotJson["front_range_m"]?.jsonPrimitive?.floatOrNull,
        )
        emitFrame()
    }

    private fun parseNavigation(payload: String) {
        val root = runCatching { json.parseToJsonElement(payload).jsonObject }.getOrNull() ?: return
        val candidates = root["candidates"]?.jsonArray.orEmpty().mapNotNull { element ->
            val item = element.jsonObject
            val position = item["position_m"]?.jsonArray ?: return@mapNotNull null
            NavigationCandidateObservation(
                type = item["type"]!!.jsonPrimitive.content,
                id = item["id"]!!.jsonPrimitive.content,
                label = item["label"]!!.jsonPrimitive.content,
                purpose = item["purpose"]!!.jsonPrimitive.content,
                x = position.floatAt(0),
                y = position.floatAt(1),
                pathLengthM = item["path_length_m"]!!.jsonPrimitive.float,
                risk = item["risk"]!!.jsonPrimitive.float,
                informationGain = item["information_gain"]!!.jsonPrimitive.float,
                capability = item["capability"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                targetRevision = item["target_revision"]?.jsonPrimitive?.longOrNull,
            )
        }
        latestNavigation = NavigationObservation(
            capturedMonotonicNs = root["captured_monotonic_ns"]!!.jsonPrimitive.long,
            sensorMapSeq = root["sensor_map_seq"]!!.jsonPrimitive.long,
            navigationRevision = root["navigation_revision"]!!.jsonPrimitive.long,
            validUntilMonotonicNs = root["valid_until_monotonic_ns"]!!.jsonPrimitive.long,
            candidates = candidates,
        )
        emitFrame()
    }

    private fun parseActionResult(payload: String) {
        val root = runCatching { json.parseToJsonElement(payload).jsonObject }.getOrNull() ?: return
        val actionId = root["action_id"]?.jsonPrimitive?.contentOrNull ?: return
        val data = root["data"]?.jsonObject.orEmpty().mapValues { (_, value) -> value.toNativeValue() }
        val result = ActionResult(
            accepted = root["accepted"]?.jsonPrimitive?.booleanOrNull ?: false,
            status = root["status"]?.jsonPrimitive?.contentOrNull ?: "UNKNOWN",
            detail = root["detail"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            data = data,
        )
        _actionEvents.tryEmit(result)
        if (result.status in HIL_TERMINAL_STATUSES) {
            pendingActions.remove(actionId)?.complete(result)
        }
    }

    private fun parseCameraInfo(message: JsonObject) {
        val intrinsics = message["k"]?.jsonArray ?: return
        if (intrinsics.size < 6) return
        latestCameraCalibration = CameraCalibration(
            width = message["width"]?.jsonPrimitive?.longOrNull?.toInt() ?: return,
            height = message["height"]?.jsonPrimitive?.longOrNull?.toInt() ?: return,
            fx = intrinsics.floatAt(0),
            fy = intrinsics.floatAt(4),
            cx = intrinsics.floatAt(2),
            cy = intrinsics.floatAt(5),
        )
        emitFrame()
    }

    private fun emitFrame() {
        val envelope = latestEnvelope ?: return
        val robot = latestRobot ?: return
        _observations.tryEmit(
            SensorFrame(
                envelope = envelope,
                robot = robot,
                navigation = latestNavigation,
                metaViewJpeg = viewBuffer.latest("META_VIEW")?.jpeg,
                egoRgbJpeg = viewBuffer.latest("EGO_RGB")?.jpeg,
                cameraCalibration = latestCameraCalibration,
            )
        )
    }

    private fun rosbridgeSubscribe(topic: String, type: String) = buildJsonObject {
        put("op", "subscribe")
        put("id", "sub-$topic")
        put("topic", topic)
        put("type", type)
        put("throttle_rate", if (topic.endsWith("compressed")) 750 else 0)
        put("queue_length", 1)
    }

    private fun rosbridgePublish(topic: String, data: JsonElement) = buildJsonObject {
        put("op", "publish")
        put("topic", topic)
        put("msg", buildJsonObject { put("data", data) })
    }

    private fun sendBestEffortStop(activeSocket: WebSocket, reason: String) {
        val action = buildJsonObject {
            put("contract_version", "pulso.action.v1")
            put("action_id", "STOP-${System.nanoTime()}")
            put("mission_id", "M-001")
            put("issued_monotonic_ns", System.nanoTime())
            put("kind", "STOP")
            put("target", JsonNull)
            put("parameters", buildJsonObject { put("reason", reason) })
        }
        activeSocket.send(
            rosbridgePublish("/pulso/hil/action_intent", JsonPrimitive(action.toString())).toString()
        )
    }

    fun latestViewBytes(requestedKind: String, capturedNs: Long): ByteArray? {
        val bufferedKind = if (requestedKind == "META_VIEW") "META_VIEW" else "EGO_RGB"
        return viewBuffer.latest(bufferedKind)
            ?.takeIf { it.capturedMonotonicNs == capturedNs }
            ?.jpeg
    }

}

private fun JsonObject.stringData(): String? = this["data"]?.jsonPrimitive?.contentOrNull

private fun JsonObject.decodedView(): Pair<Long, ByteArray>? {
    val stamp = this["header"]?.jsonObject?.get("stamp")?.jsonObject ?: return null
    val seconds = stamp["sec"]?.jsonPrimitive?.longOrNull ?: return null
    val nanoseconds = stamp["nanosec"]?.jsonPrimitive?.longOrNull ?: return null
    val encoded = this["data"]?.jsonPrimitive?.contentOrNull ?: return null
    return (seconds * 1_000_000_000L + nanoseconds) to Base64.decode(encoded, Base64.DEFAULT)
}

private fun JsonArray.floatAt(index: Int): Float = get(index).jsonPrimitive.float

private fun Any?.toJsonElement(): JsonElement = when (this) {
    null -> JsonNull
    is Boolean -> JsonPrimitive(this)
    is Number -> JsonPrimitive(this)
    else -> JsonPrimitive(toString())
}

private fun JsonElement.toNativeValue(): Any = when (this) {
    is JsonPrimitive -> booleanOrNull ?: longOrNull ?: floatOrNull ?: content
    else -> toString()
}
