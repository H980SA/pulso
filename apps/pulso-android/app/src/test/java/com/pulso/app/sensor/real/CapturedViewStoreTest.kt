package com.pulso.app.sensor.real

import com.pulso.app.sensor.CameraCalibration
import com.pulso.app.sensor.NavigationObservation
import com.pulso.app.sensor.ObservationEnvelope
import com.pulso.app.sensor.RobotObservation
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.SensorMode
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CapturedViewStoreTest {
    @Test
    fun jpegLookupAndSceneJsonShareTheAuthorizedCaptureTimestamp() {
        val capturedNs = 8_123_456_789L
        val store = CapturedViewStore(capacity = 2)
        store.put(frame(capturedNs), scene(capturedNs))

        val exact = store.exact(capturedNs)!!

        assertEquals(capturedNs, exact.capturedMonotonicNs)
        assertArrayEquals(byteArrayOf(1, 2, 3), exact.bytes("CANDIDATE_VIEW"))
        assertTrue(exact.sceneJson.contains("\"captured_monotonic_ns\":$capturedNs"))
        assertEquals(null, store.exact(capturedNs + 1))
    }

    @Test(expected = IllegalArgumentException::class)
    fun mismatchedFrameAndSceneAreRejected() {
        CapturedViewStore(2).put(frame(10), scene(11))
    }

    private fun frame(capturedNs: Long) = SensorFrame(
        envelope = ObservationEnvelope(
            observationId = "REAL-$capturedNs",
            source = SensorMode.ANDROID_REAL,
            capturedMonotonicNs = capturedNs,
            frameId = "arcore_world",
            trackingState = "TRACKING",
            trackingQuality = 1f,
            trackingEpoch = 1,
            artifactUris = emptyMap(),
        ),
        robot = RobotObservation(0f, 0f, 0f, 1f, "STOPPED", 1f, false, 1f),
        navigation = null,
        metaViewJpeg = byteArrayOf(4, 5, 6),
        egoRgbJpeg = byteArrayOf(1, 2, 3),
        cameraCalibration = CameraCalibration(10, 10, 5f, 5f, 5f, 5f),
    )

    private fun scene(capturedNs: Long): MetaViewScene {
        val map = LocalMapSnapshot(1, capturedNs, 0.25f, emptyList(), emptyList(), emptyList())
        val navigation = NavigationObservation(capturedNs, 1, 1, capturedNs + 15_000_000_000L, emptyList())
        return MetaViewScene("{\"captured_monotonic_ns\":$capturedNs}", navigation, map)
    }
}
