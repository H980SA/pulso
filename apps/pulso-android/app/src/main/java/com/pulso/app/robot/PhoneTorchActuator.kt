package com.pulso.app.robot

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Handler
import android.os.Looper
import com.pulso.app.tools.ActionResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout

/** Camera2 torch adapter that reports success only after the platform callback confirms the state. */
class PhoneTorchActuator(context: Context) : AutoCloseable {
    private val cameraManager = context.applicationContext.getSystemService(CameraManager::class.java)
    private val cameraId = cameraManager.cameraIdList.firstOrNull { id ->
        cameraManager.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
    }
    @Volatile private var state: Boolean? = if (cameraId == null) false else null
    @Volatile private var unavailable = cameraId == null
    private val lock = Any()
    private var pending: Pair<Boolean, CompletableDeferred<Boolean>>? = null

    private val callback = object : CameraManager.TorchCallback() {
        override fun onTorchModeChanged(id: String, enabled: Boolean) {
            if (id != cameraId) return
            state = enabled
            unavailable = false
            synchronized(lock) {
                pending?.takeIf { it.first == enabled }?.second?.complete(enabled)
            }
        }

        override fun onTorchModeUnavailable(id: String) {
            if (id != cameraId) return
            state = null
            unavailable = true
            synchronized(lock) { pending?.second?.completeExceptionally(IllegalStateException("Torch unavailable")) }
        }
    }

    init {
        if (cameraId != null) cameraManager.registerTorchCallback(callback, Handler(Looper.getMainLooper()))
    }

    fun confirmedState(): Boolean? = state

    suspend fun setEnabled(enabled: Boolean): ActionResult {
        val id = cameraId ?: return ActionResult(false, "TORCH_UNSUPPORTED", "This phone has no reported flash unit.")
        if (unavailable) return ActionResult(false, "TORCH_UNAVAILABLE", "The camera service reports the torch unavailable.")
        if (state == enabled) return ActionResult(true, "CONFIRMED", "Torch is already ${if (enabled) "on" else "off"}.")
        val confirmation = CompletableDeferred<Boolean>()
        synchronized(lock) { pending = enabled to confirmation }
        val requestFailure = runCatching { cameraManager.setTorchMode(id, enabled) }.exceptionOrNull()
        if (requestFailure != null) {
            synchronized(lock) { pending = null }
            return ActionResult(false, "TORCH_REQUEST_FAILED", requestFailure.message ?: requestFailure::class.java.simpleName)
        }
        val confirmed = runCatching { withTimeout(CONFIRM_TIMEOUT_MS) { confirmation.await() } }
        synchronized(lock) { pending = null }
        return confirmed.fold(
            onSuccess = { ActionResult(true, "CONFIRMED", "Camera2 confirmed torch ${if (it) "on" else "off"}.") },
            onFailure = { ActionResult(false, "TORCH_CONFIRMATION_FAILED", it.message ?: "No torch callback arrived.") },
        )
    }

    override fun close() {
        runCatching { cameraId?.let { cameraManager.setTorchMode(it, false) } }
        runCatching { cameraManager.unregisterTorchCallback(callback) }
        synchronized(lock) { pending?.second?.cancel(); pending = null }
    }

    private companion object { const val CONFIRM_TIMEOUT_MS = 2_000L }
}

