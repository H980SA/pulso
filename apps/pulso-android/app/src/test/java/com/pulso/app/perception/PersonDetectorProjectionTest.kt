package com.pulso.app.perception

import com.pulso.app.sensor.CameraCalibration
import kotlin.math.abs
import org.junit.Assert.assertTrue
import org.junit.Test

class PersonDetectorProjectionTest {
    private val calibration = CameraCalibration(
        width = 640,
        height = 480,
        fx = 554.3f,
        fy = 554.3f,
        cx = 320f,
        cy = 240f,
    )

    @Test
    fun opticalCenterIsZeroBearing() {
        assertTrue(abs(bearingDegrees(320f, 640, calibration)) < 0.01f)
    }

    @Test
    fun calibrationScalesWithJpegResolution() {
        val native = bearingDegrees(480f, 640, calibration)
        val halfSize = bearingDegrees(240f, 320, calibration)
        assertTrue(abs(native - halfSize) < 0.01f)
        assertTrue(native > 15f)
    }

    @Test
    fun overlappingPoseBoxesAreSuppressedByConfidence() {
        val stronger = pose(0.82f, 10f, 10f, 110f, 210f)
        val duplicate = pose(0.44f, 14f, 12f, 108f, 208f)
        val separate = pose(0.31f, 180f, 20f, 260f, 180f)
        val selected = nonMaximumSuppression(
            listOf(duplicate, separate, stronger),
            iouThreshold = 0.45f,
            maxResults = 4,
        )
        assertTrue(selected == listOf(stronger, separate))
    }

    private fun pose(
        confidence: Float,
        left: Float,
        top: Float,
        right: Float,
        bottom: Float,
    ) = PoseCandidate(confidence, left, top, right, bottom, visibleKeypoints = 6)
}
