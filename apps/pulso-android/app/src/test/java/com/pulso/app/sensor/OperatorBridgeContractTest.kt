package com.pulso.app.sensor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OperatorBridgeContractTest {
    @Test
    fun observationMirrorOmitsArtifactsOwnedBySeparateTopics() {
        val frame = SensorFrame(
            envelope = ObservationEnvelope(
                observationId = "REAL-1",
                source = SensorMode.ANDROID_REAL,
                capturedMonotonicNs = 123L,
                frameId = "arcore_world",
                trackingState = "TRACKING",
                trackingQuality = 1f,
                trackingEpoch = 2L,
                artifactUris = mapOf("META_VIEW_SCENE" to "pulso://metaview-scene/7"),
            ),
            robot = RobotObservation(
                x = 1f,
                y = 2f,
                headingDeg = 90f,
                poseConfidence = 1f,
                motionState = "STOPPED",
                batteryFraction = 0.5f,
                flashlightOn = false,
                frontRangeM = null,
            ),
            navigation = null,
            metaViewJpeg = null,
            egoRgbJpeg = null,
            cameraCalibration = null,
        )

        val payload = observationPayload(frame)

        assertEquals("pulso.observation.v1", payload["contract_version"]?.toString()?.trim('"'))
        assertNotNull(payload["tracking"])
        assertNotNull(payload["robot"])
        assertFalse("artifacts" in payload)
    }

    @Test
    fun publishesVersionedMeasuredPhoneTelemetryAndCameraIntrinsics() {
        val frame = realFrame()

        val telemetry = phoneTelemetryPayload(frame)
        val cameraInfo = cameraInfoPayload(frame)

        assertEquals("pulso.phone-telemetry.v1", telemetry?.get("contract_version")?.toString()?.trim('"'))
        assertEquals("[0.1,0.2,9.7]", telemetry?.get("imu")?.let { it as kotlinx.serialization.json.JsonObject }?.get("acceleration_mps2").toString())
        assertTrue(telemetry?.get("battery").toString().contains("37.5"))
        assertEquals("pulso.phone-camera-info.v1", cameraInfo?.get("contract_version")?.toString()?.trim('"'))
        assertTrue(cameraInfo?.get("k").toString().contains("612.0"))
    }

    @Test
    fun absentRealEvidenceIsOmittedInsteadOfManufactured() {
        val frame = realFrame().copy(phoneTelemetry = null, cameraCalibration = null)

        assertNull(phoneTelemetryPayload(frame))
        assertNull(cameraInfoPayload(frame))
    }

    @Test
    fun hilCalibrationIsNotRepublishedOverItsNativeRosCameraInfoTopic() {
        val hilFrame = realFrame().copy(
            envelope = realFrame().envelope.copy(source = SensorMode.GAZEBO_HIL),
        )

        assertNull(cameraInfoPayload(hilFrame))
    }

    private fun realFrame() = SensorFrame(
        envelope = ObservationEnvelope(
            observationId = "REAL-2",
            source = SensorMode.ANDROID_REAL,
            capturedMonotonicNs = 8_000_000_000L,
            frameId = "arcore_world",
            trackingState = "TRACKING",
            trackingQuality = 1f,
            trackingEpoch = 3L,
            artifactUris = emptyMap(),
        ),
        robot = RobotObservation(1f, 2f, 90f, 1f, "STOPPED", 0.72f, false, 1.4f),
        navigation = null,
        metaViewJpeg = null,
        egoRgbJpeg = null,
        cameraCalibration = CameraCalibration(1920, 1080, 612f, 611f, 960f, 540f),
        phoneTelemetry = PhoneTelemetryObservation(
            imuCapturedMonotonicNs = 7_999_000_000L,
            accelerationMps2 = listOf(0.1f, 0.2f, 9.7f),
            angularVelocityRadps = listOf(0.01f, 0.02f, 0.03f),
            batteryTemperatureC = 37.5f,
        ),
    )
}
