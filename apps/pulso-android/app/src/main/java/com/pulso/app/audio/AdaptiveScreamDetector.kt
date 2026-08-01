package com.pulso.app.audio

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.sqrt

data class AcousticAlert(
    val id: String,
    val capturedMonotonicNs: Long,
    val confidence: Float,
    val durationMs: Long,
    val rmsDbfs: Float,
    val marginAboveNoiseDb: Float,
    val bearingKnown: Boolean = false,
)

data class AudioWindowMetrics(
    val sequence: Long,
    val capturedMonotonicNs: Long,
    val rmsDbfs: Float,
    val peakFraction: Float,
    val zeroCrossingRate: Float,
    val noiseFloorDbfs: Float,
    val screamCandidate: Boolean,
)

/** Pure adaptive detector for a deliberately loud, sustained vocal alarm in a noisy room. */
class AdaptiveScreamDetector(private val sampleRateHz: Int = 16_000) {
    private var noiseFloorDbfs = INITIAL_NOISE_FLOOR_DBFS
    private var hotSamples = 0L
    private var cooldownUntilNs = 0L
    private var sequence = 0L

    fun process(
        samples: ShortArray,
        count: Int,
        capturedMonotonicNs: Long,
        suppressed: Boolean = false,
    ): Pair<AudioWindowMetrics, AcousticAlert?> {
        require(count in 1..samples.size)
        var sumSquares = 0.0
        var peak = 0
        var crossings = 0
        var previous = samples[0].toInt()
        for (index in 0 until count) {
            val value = samples[index].toInt()
            sumSquares += value.toDouble() * value
            peak = maxOf(peak, abs(value))
            if (index > 0 && (value >= 0) != (previous >= 0)) crossings += 1
            previous = value
        }
        val rmsFraction = sqrt(sumSquares / count) / Short.MAX_VALUE
        val rmsDbfs = (20.0 * log10(rmsFraction.coerceAtLeast(0.000001))).toFloat()
        val peakFraction = peak.toFloat() / Short.MAX_VALUE
        val zeroCrossingRate = crossings.toFloat() / count
        val margin = rmsDbfs - noiseFloorDbfs
        val hot = !suppressed &&
            capturedMonotonicNs >= cooldownUntilNs &&
            rmsDbfs >= MIN_ABSOLUTE_RMS_DBFS &&
            margin >= MIN_MARGIN_ABOVE_NOISE_DB &&
            peakFraction >= MIN_PEAK_FRACTION &&
            zeroCrossingRate in MIN_ZERO_CROSSING_RATE..MAX_ZERO_CROSSING_RATE

        if (suppressed) {
            hotSamples = 0
        } else if (hot) {
            hotSamples += count
        } else {
            hotSamples = 0
            val alpha = if (rmsDbfs < noiseFloorDbfs) FAST_FLOOR_ALPHA else SLOW_FLOOR_ALPHA
            noiseFloorDbfs += alpha * (rmsDbfs - noiseFloorDbfs)
            noiseFloorDbfs = noiseFloorDbfs.coerceIn(MIN_NOISE_FLOOR_DBFS, MAX_NOISE_FLOOR_DBFS)
        }

        val durationMs = hotSamples * 1_000 / sampleRateHz
        val alert = if (hot && durationMs >= MIN_SCREAM_DURATION_MS) {
            cooldownUntilNs = capturedMonotonicNs + COOLDOWN_NS
            hotSamples = 0
            AcousticAlert(
                id = "ACOUSTIC-$capturedMonotonicNs",
                capturedMonotonicNs = capturedMonotonicNs,
                confidence = confidence(rmsDbfs, margin, durationMs),
                durationMs = durationMs,
                rmsDbfs = rmsDbfs,
                marginAboveNoiseDb = margin,
            )
        } else {
            null
        }
        sequence += 1
        return AudioWindowMetrics(
            sequence = sequence,
            capturedMonotonicNs = capturedMonotonicNs,
            rmsDbfs = rmsDbfs,
            peakFraction = peakFraction,
            zeroCrossingRate = zeroCrossingRate,
            noiseFloorDbfs = noiseFloorDbfs,
            screamCandidate = hot,
        ) to alert
    }

    private fun confidence(rmsDbfs: Float, margin: Float, durationMs: Long): Float {
        val loudness = ((rmsDbfs - MIN_ABSOLUTE_RMS_DBFS) / 14f).coerceIn(0f, 1f)
        val separation = ((margin - MIN_MARGIN_ABOVE_NOISE_DB) / 18f).coerceIn(0f, 1f)
        val duration = ((durationMs - MIN_SCREAM_DURATION_MS) / 700f).coerceIn(0f, 1f)
        return (0.45f + loudness * 0.2f + separation * 0.25f + duration * 0.1f).coerceIn(0f, 0.98f)
    }

    companion object {
        const val MIN_SCREAM_DURATION_MS = 320L
        private const val MIN_ABSOLUTE_RMS_DBFS = -20f
        private const val MIN_MARGIN_ABOVE_NOISE_DB = 15f
        private const val MIN_PEAK_FRACTION = 0.48f
        private const val MIN_ZERO_CROSSING_RATE = 0.015f
        private const val MAX_ZERO_CROSSING_RATE = 0.38f
        private const val INITIAL_NOISE_FLOOR_DBFS = -52f
        private const val MIN_NOISE_FLOOR_DBFS = -70f
        private const val MAX_NOISE_FLOOR_DBFS = -24f
        private const val SLOW_FLOOR_ALPHA = 0.025f
        private const val FAST_FLOOR_ALPHA = 0.12f
        private const val COOLDOWN_NS = 4_000_000_000L
    }
}
