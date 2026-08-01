package com.pulso.app.audio

import kotlin.math.PI
import kotlin.math.sin
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class AdaptiveScreamDetectorTest {
    @Test
    fun quietAndOrdinaryNoiseDoNotTrigger() {
        val detector = AdaptiveScreamDetector()
        var now = 1_000_000_000L
        repeat(20) {
            val noise = ShortArray(1_024) { index -> ((index * 17 % 900) - 450).toShort() }
            val (metrics, alert) = detector.process(noise, noise.size, now)
            assertFalse(metrics.screamCandidate)
            assertNull(alert)
            now += 64_000_000L
        }
    }

    @Test
    fun deliberateLoudSustainedVocalLikeToneTriggersOnce() {
        val detector = AdaptiveScreamDetector()
        var now = 1_000_000_000L
        repeat(10) {
            val baseline = ShortArray(1_024) { index -> ((index * 7 % 500) - 250).toShort() }
            detector.process(baseline, baseline.size, now)
            now += 64_000_000L
        }
        var alert: AcousticAlert? = null
        repeat(8) { window ->
            val loud = ShortArray(1_024) { index ->
                (sin(2.0 * PI * 620.0 * index / 16_000.0) * 25_000).toInt().toShort()
            }
            alert = alert ?: detector.process(loud, loud.size, now + window * 64_000_000L).second
        }
        assertNotNull(alert)
    }

    @Test
    fun ttsSuppressionPreventsSelfTrigger() {
        val detector = AdaptiveScreamDetector()
        var alert: AcousticAlert? = null
        repeat(10) { window ->
            val loud = ShortArray(1_024) { index ->
                (sin(2.0 * PI * 700.0 * index / 16_000.0) * 27_000).toInt().toShort()
            }
            alert = alert ?: detector.process(loud, loud.size, 1_000_000_000L + window * 64_000_000L, suppressed = true).second
        }
        assertNull(alert)
    }
}
