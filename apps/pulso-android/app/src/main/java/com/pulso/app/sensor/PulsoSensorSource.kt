package com.pulso.app.sensor

import kotlinx.coroutines.flow.Flow

enum class SensorMode { DISCONNECTED, REPLAY, GAZEBO_HIL, ANDROID_REAL }

data class ObservationEnvelope(
    val contractVersion: String = "pulso.observation.v1",
    val observationId: String,
    val source: SensorMode,
    val capturedMonotonicNs: Long,
    val frameId: String,
    val trackingState: String,
    val trackingQuality: Float,
    val trackingEpoch: Long,
    val artifactUris: Map<String, String>,
)

data class RobotObservation(
    val x: Float,
    val y: Float,
    val headingDeg: Float,
    val poseConfidence: Float,
    val motionState: String,
    val batteryFraction: Float,
    val flashlightOn: Boolean,
    val frontRangeM: Float?,
)

data class NavigationCandidateObservation(
    val type: String,
    val id: String,
    val label: String,
    val purpose: String,
    val x: Float,
    val y: Float,
    val pathLengthM: Float,
    val risk: Float,
    val informationGain: Float,
    val capability: String = "",
    val targetRevision: Long? = null,
)

data class NavigationObservation(
    val capturedMonotonicNs: Long,
    val sensorMapSeq: Long,
    val navigationRevision: Long,
    val validUntilMonotonicNs: Long,
    val candidates: List<NavigationCandidateObservation>,
)

data class CameraCalibration(
    val width: Int,
    val height: Int,
    val fx: Float,
    val fy: Float,
    val cx: Float,
    val cy: Float,
)

data class PhoneTelemetryObservation(
    val imuCapturedMonotonicNs: Long?,
    val accelerationMps2: List<Float>?,
    val angularVelocityRadps: List<Float>?,
    val batteryTemperatureC: Float?,
)

data class DepthSampleObservation(
    val uNorm: Float,
    val vNorm: Float,
    val rangeM: Float,
)

data class PerceptionTrackObservation(
    val id: String,
    val label: String,
    val modelId: String,
    val confidence: Float,
    val bearingDeg: Float,
    val leftNorm: Float,
    val topNorm: Float,
    val rightNorm: Float,
    val bottomNorm: Float,
    val revision: Long,
    val inferenceLatencyMs: Long,
    val visibleKeypoints: Int,
)

data class SensorFrame(
    val envelope: ObservationEnvelope,
    val robot: RobotObservation,
    val navigation: NavigationObservation?,
    val metaViewJpeg: ByteArray?,
    val egoRgbJpeg: ByteArray?,
    val cameraCalibration: CameraCalibration?,
    val phoneTelemetry: PhoneTelemetryObservation? = null,
    val depthSamples: List<DepthSampleObservation> = emptyList(),
    /** Lightweight live preview for Mission Control; cognition keeps [egoRgbJpeg]. */
    val operatorRgbJpeg: ByteArray? = null,
)

interface PulsoSensorSource : AutoCloseable {
    val mode: SensorMode
    val observations: Flow<SensorFrame>
    suspend fun start()
    suspend fun stop()
    override fun close() {}
}
