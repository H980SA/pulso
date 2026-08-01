package com.pulso.app.perception

import android.content.Context
import com.pulso.app.sensor.CameraCalibration
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Owns detector lifetime, frame deduplication, and off-main-thread inference. */
class PersonPerceptionRunner(private val context: Context) : AutoCloseable {
    private var detector: PersonDetector? = null
    private var job: Job? = null
    private var lastRgbHash: Int? = null

    fun submit(
        scope: CoroutineScope,
        jpeg: ByteArray,
        calibration: CameraCalibration?,
        onWarming: () -> Unit,
        onResult: (List<PersonDetection>) -> Unit,
        onFailure: (Throwable) -> Unit,
    ) {
        val hash = jpeg.contentHashCode()
        if (hash == lastRgbHash || job?.isActive == true) return
        lastRgbHash = hash
        job = scope.launch {
            if (detector == null) onWarming()
            runCatching {
                withContext(Dispatchers.Default) {
                    val active = detector ?: PersonDetector(context).also { detector = it }
                    active.detect(jpeg, calibration)
                }
            }.onSuccess(onResult).onFailure(onFailure)
        }
    }

    override fun close() {
        job?.cancel()
        detector?.close()
    }
}
