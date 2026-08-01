package com.pulso.app.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.core.content.ContextCompat
import com.pulso.app.tools.ActionResult
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

/** Android TTS plus a single continuous, non-persisted microphone stream. */
class PhoneAudioActuator(context: Context) : AutoCloseable {
    private val appContext = context.applicationContext
    private val initialized = CompletableDeferred<Int>()
    private val utterances = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lifecycleMutex = Mutex()
    private val detector = AdaptiveScreamDetector(SAMPLE_RATE)
    private val metricsLock = Any()
    private val recentMetrics = ArrayDeque<AudioWindowMetrics>()
    private val suppressedUntilNs = AtomicLong(0L)
    private val _alerts = MutableSharedFlow<AcousticAlert>(extraBufferCapacity = 8)
    val alerts: SharedFlow<AcousticAlert> = _alerts.asSharedFlow()
    @Volatile private var recorder: AudioRecord? = null
    @Volatile private var monitoringJob: Job? = null
    private var tts: TextToSpeech? = null

    init {
        tts = TextToSpeech(appContext) { status -> initialized.complete(status) }.also { engine ->
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String) {
                    suppressedUntilNs.set(Long.MAX_VALUE)
                }

                override fun onDone(utteranceId: String) {
                    endTtsSuppression()
                    utterances.remove(utteranceId)?.complete(Unit)
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String) {
                    endTtsSuppression()
                    utterances.remove(utteranceId)?.completeExceptionally(IllegalStateException("TTS synthesis failed"))
                }

                override fun onError(utteranceId: String, errorCode: Int) {
                    endTtsSuppression()
                    utterances.remove(utteranceId)?.completeExceptionally(IllegalStateException("TTS error $errorCode"))
                }
            })
        }
    }

    suspend fun startMonitoring() = lifecycleMutex.withLock {
        if (monitoringJob?.isActive == true) return@withLock
        requireMicrophonePermission()
        val audioRecord = openRecorder()
        recorder = audioRecord
        monitoringJob = scope.launch { monitor(audioRecord) }
    }

    suspend fun stopMonitoring() = lifecycleMutex.withLock {
        val active = monitoringJob
        monitoringJob = null
        runCatching { recorder?.stop() }
        active?.cancelAndJoin()
        recorder?.release()
        recorder = null
    }

    suspend fun speak(text: String): ActionResult {
        val phrase = text.trim()
        if (phrase.isEmpty() || phrase.length > MAX_SPEECH_CHARS) {
            return ActionResult(false, "INVALID_ARGUMENT", "Speech must contain 1–$MAX_SPEECH_CHARS characters.")
        }
        val init = runCatching { withTimeout(TTS_INIT_TIMEOUT_MS) { initialized.await() } }.getOrNull()
        if (init != TextToSpeech.SUCCESS) return ActionResult(false, "TTS_UNAVAILABLE", "Android TTS did not initialize successfully.")
        val engine = tts ?: return ActionResult(false, "TTS_CLOSED", "Android TTS is closed.")
        engine.language = Locale.getDefault()
        val id = "pulso-${UUID.randomUUID()}"
        val completion = CompletableDeferred<Unit>()
        utterances[id] = completion
        if (engine.speak(phrase, TextToSpeech.QUEUE_FLUSH, null, id) != TextToSpeech.SUCCESS) {
            utterances.remove(id)
            endTtsSuppression()
            return ActionResult(false, "TTS_START_FAILED", "Android TTS rejected the utterance.")
        }
        return runCatching { withTimeout(TTS_COMPLETE_TIMEOUT_MS) { completion.await() } }.fold(
            onSuccess = { ActionResult(true, "CONFIRMED", "Android TTS confirmed utterance completion.") },
            onFailure = { ActionResult(false, "TTS_COMPLETION_FAILED", it.message ?: "No completion callback arrived.") },
        )
    }

    suspend fun listen(durationSeconds: Int): ActionResult {
        if (durationSeconds !in 1..8) return ActionResult(false, "INVALID_ARGUMENT", "Listen duration must be 1–8 seconds.")
        if (monitoringJob?.isActive != true) {
            return ActionResult(false, "MICROPHONE_NOT_MONITORING", "Continuous microphone monitoring is not active.")
        }
        val startSequence = synchronized(metricsLock) { recentMetrics.lastOrNull()?.sequence ?: 0L }
        delay(durationSeconds * 1_000L)
        val windows = synchronized(metricsLock) { recentMetrics.filter { it.sequence > startSequence } }
        if (windows.isEmpty()) return ActionResult(false, "NO_AUDIO_CAPTURED", "The continuous monitor returned no fresh windows.")
        return ActionResult(
            accepted = true,
            status = "CAPTURED",
            detail = "Analyzed ${windows.size} fresh PCM windows from the continuous monitor; raw audio was not persisted.",
            data = mapOf(
                "sample_rate_hz" to SAMPLE_RATE,
                "window_count" to windows.size,
                "max_rms_dbfs" to windows.maxOf { it.rmsDbfs },
                "noise_floor_dbfs" to windows.last().noiseFloorDbfs,
                "scream_candidate_windows" to windows.count { it.screamCandidate },
                "bearing_known" to false,
            ),
        )
    }

    override fun close() {
        monitoringJob?.cancel()
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        scope.cancel()
        utterances.values.forEach { it.cancel() }
        utterances.clear()
        tts?.stop()
        tts?.shutdown()
        tts = null
    }

    private suspend fun monitor(audioRecord: AudioRecord) = withContext(Dispatchers.IO) {
        val samples = ShortArray(WINDOW_SAMPLES)
        audioRecord.startRecording()
        try {
            while (isActive) {
                val read = audioRecord.read(samples, 0, samples.size, AudioRecord.READ_BLOCKING)
                if (read <= 0) continue
                val nowNs = SystemClock.elapsedRealtimeNanos()
                val suppressed = nowNs < suppressedUntilNs.get()
                val (metrics, alert) = detector.process(samples, read, nowNs, suppressed)
                synchronized(metricsLock) {
                    recentMetrics.addLast(metrics)
                    while (recentMetrics.size > MAX_RECENT_WINDOWS) recentMetrics.removeFirst()
                }
                if (alert != null) _alerts.tryEmit(alert)
            }
        } finally {
            runCatching { audioRecord.stop() }
        }
    }

    private fun requireMicrophonePermission() {
        check(
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
        ) { "RECORD_AUDIO permission is not granted" }
    }

    private fun openRecorder(): AudioRecord {
        val minimum = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        check(minimum > 0) { "No supported PCM input buffer is available" }
        val instance = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minimum * 2, WINDOW_SAMPLES * 2),
        )
        check(instance.state == AudioRecord.STATE_INITIALIZED) {
            instance.release()
            "AudioRecord did not initialize"
        }
        return instance
    }

    private fun endTtsSuppression() {
        suppressedUntilNs.set(SystemClock.elapsedRealtimeNanos() + POST_TTS_SUPPRESSION_NS)
    }

    private companion object {
        const val SAMPLE_RATE = 16_000
        const val WINDOW_SAMPLES = 1_024
        const val MAX_RECENT_WINDOWS = 160
        const val MAX_SPEECH_CHARS = 240
        const val TTS_INIT_TIMEOUT_MS = 5_000L
        const val TTS_COMPLETE_TIMEOUT_MS = 20_000L
        const val POST_TTS_SUPPRESSION_NS = 800_000_000L
    }
}
