package com.pulso.app.robot

import com.pulso.app.tools.ActionResult
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/**
 * Independent Zeus transport with a 300 ms client watchdog. Live drive frames require explicit
 * arm(), an explicitly present operator, and a separately verified firmware dead-man. The stock wire protocol has no STOP ACK, and
 * an Android process or Wi-Fi failure can defeat a client-only TTL, so STOP is never reported as
 * confirmed. Dry-run is the only mode covered by local verification.
 */
class ZeusWebSocketClient(
    private val url: String = DEFAULT_URL,
    val dryRun: Boolean = true,
    private val firmwareDeadmanVerified: Boolean = false,
) : AutoCloseable {
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .pingInterval(1, TimeUnit.SECONDS)
        .build()
    private val watchdog = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "pulso-zeus-watchdog").apply { isDaemon = true }
    }
    private val lastMotionCommandNs = AtomicLong(0L)
    private val armGate = ZeusArmGate()
    @Volatile private var socket: WebSocket? = null
    @Volatile private var lastSafetyStatus = "DISCONNECTED"
    private var connection = CompletableDeferred<Unit>()

    init {
        require(url == DEFAULT_URL || url.startsWith("ws://") || url.startsWith("wss://")) { "Zeus URL must be WebSocket." }
        watchdog.scheduleWithFixedDelay(::enforceTtl, 50, 50, TimeUnit.MILLISECONDS)
    }

    suspend fun connect(): ActionResult {
        if (socket != null) return ActionResult(armGate.connected, if (armGate.connected) "CONNECTED" else "CONNECTING", lastSafetyStatus)
        connection = CompletableDeferred()
        socket = client.newWebSocket(Request.Builder().url(url).build(), Listener())
        return runCatching { withTimeout(CONNECT_TIMEOUT_MS) { connection.await() } }.fold(
            onSuccess = { ActionResult(true, "CONNECTED_STOP_UNCONFIRMED", "Connected to Zeus; STOP was queued without protocol ACK and arm state is false.", statusData()) },
            onFailure = {
                disarm("CONNECT_FAILED")
                ActionResult(false, "CONNECT_FAILED", it.message ?: "Zeus connection timed out.", statusData())
            },
        )
    }

    fun arm(operatorPresent: Boolean = false): ActionResult {
        if (!armGate.arm()) return ActionResult(false, "NOT_CONNECTED", "Connect to Zeus before arming.", statusData())
        if (!dryRun && (!firmwareDeadmanVerified || !operatorPresent)) {
            armGate.disarm()
            return ActionResult(
                false,
                "LIVE_INTERLOCK_REQUIRED",
                "Live motion requires a verified firmware dead-man and an explicitly present human operator.",
                statusData(),
            )
        }
        lastSafetyStatus = if (dryRun) "ARMED_DRY_RUN" else "ARMED_LIVE"
        return ActionResult(true, lastSafetyStatus, "Explicit arm accepted; 300 ms command TTL is active.", statusData())
    }

    fun disarm(reason: String = "OPERATOR_DISARM"): ActionResult {
        armGate.disarm()
        val queued = sendStop(reason)
        return ActionResult(
            false,
            "DISARMED_STOP_UNCONFIRMED",
            "Local arm was cleared; STOP ${if (queued) "was queued" else "could not be queued"} and Zeus provides no ACK.",
            statusData() + ("stop_confirmed" to false),
        )
    }

    fun command(command: ZeusCommand): ActionResult {
        if (command == ZeusCommand.Stop) {
            val queued = sendStop("COMMAND_STOP")
            return ActionResult(
                false,
                "STOP_ATTEMPTED_UNCONFIRMED",
                "STOP ${if (queued) "was queued" else "could not be queued"}; this Zeus protocol has no actuator ACK.",
                statusData() + ("stop_confirmed" to false),
            )
        }
        if (!armGate.connected) return ActionResult(false, "DISCONNECTED", "Zeus is not connected.", statusData())
        if (!armGate.maySendMotion) return ActionResult(false, "NOT_ARMED", "Explicit arm() is required before motion.", statusData())
        lastMotionCommandNs.set(System.nanoTime())
        if (dryRun) {
            lastSafetyStatus = "DRY_RUN_COMMAND"
            return ActionResult(true, "DRY_RUN", "Bounded command validated but not sent to motors.", statusData(command))
        }
        val accepted = socket?.send(ZeusWireProtocol.encode(command)) == true
        if (!accepted) {
            disarm("SEND_FAILED")
            return ActionResult(false, "SEND_FAILED", "WebSocket rejected the drive frame; STOP attempted.", statusData())
        }
        lastSafetyStatus = "MOTION_FRAME_SENT"
        return ActionResult(true, "COMMAND_SENT", "One bounded drive frame sent; refresh before TTL.", statusData(command))
    }

    fun safetyStatus(): Map<String, Any> = statusData()

    fun disconnect(): ActionResult {
        disarm("DISCONNECT")
        socket?.close(1000, "Pulso Zeus disconnect")
        socket = null
        armGate.disconnected()
        lastSafetyStatus = "DISCONNECTED_STOP_ATTEMPTED"
        return ActionResult(false, "DISCONNECTED_STOP_UNCONFIRMED", "Disconnected after an unconfirmed STOP attempt.", statusData())
    }

    override fun close() {
        disconnect()
        socket?.cancel()
        watchdog.shutdownNow()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }

    private fun enforceTtl() {
        val last = lastMotionCommandNs.get()
        if (last == 0L || System.nanoTime() - last <= COMMAND_TTL_NS) return
        if (lastMotionCommandNs.compareAndSet(last, 0L)) {
            sendStop("COMMAND_TTL_EXPIRED")
            armGate.disarm()
            lastSafetyStatus = "TTL_STOP_UNCONFIRMED"
        }
    }

    private fun sendStop(reason: String): Boolean {
        lastMotionCommandNs.set(0L)
        val queued = socket?.send(ZeusWireProtocol.encode(ZeusCommand.Stop)) == true
        lastSafetyStatus = "${reason}_${if (queued) "QUEUED" else "NOT_QUEUED"}_UNCONFIRMED"
        return queued
    }

    private fun statusData(command: ZeusCommand? = null): Map<String, Any> = buildMap {
        put("url", url)
        put("connected", armGate.connected)
        put("armed", armGate.armed)
        put("dry_run", dryRun)
        put("command_ttl_ms", COMMAND_TTL_MS)
        put("firmware_deadman_verified", firmwareDeadmanVerified)
        put("stop_ack_supported", false)
        put("safety_status", lastSafetyStatus)
        if (command != null) put("bounded_command", command.toString())
    }

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            armGate.connected()
            sendStop("CONNECTED_STOP")
            connection.complete(Unit)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            sendStop("REMOTE_CLOSING")
            armGate.disarm()
            webSocket.close(code, reason)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            armGate.disconnected()
            lastSafetyStatus = "CLOSED_STOP_ATTEMPTED"
            socket = null
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            sendStop("FAILURE_STOP_ATTEMPTED")
            armGate.disconnected()
            socket = null
            if (!connection.isCompleted) connection.completeExceptionally(t)
        }
    }

    companion object {
        const val DEFAULT_URL = "ws://192.168.4.1:8765"
        const val COMMAND_TTL_MS = 300L
        private const val COMMAND_TTL_NS = COMMAND_TTL_MS * 1_000_000L
        private const val CONNECT_TIMEOUT_MS = 4_000L
    }
}

internal class ZeusArmGate {
    @Volatile var connected: Boolean = false
        private set
    @Volatile var armed: Boolean = false
        private set
    val maySendMotion: Boolean get() = connected && armed

    @Synchronized fun connected() {
        connected = true
        armed = false
    }

    @Synchronized fun arm(): Boolean {
        if (!connected) return false
        armed = true
        return true
    }

    @Synchronized fun disarm() { armed = false }

    @Synchronized fun disconnected() {
        armed = false
        connected = false
    }
}
