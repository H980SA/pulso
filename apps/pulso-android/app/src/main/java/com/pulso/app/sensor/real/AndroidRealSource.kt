package com.pulso.app.sensor.real

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.SystemClock
import android.view.Surface
import androidx.core.content.ContextCompat
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Camera
import com.google.ar.core.Config
import com.google.ar.core.Frame
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.ar.core.exceptions.NotYetAvailableException
import com.pulso.app.sensor.CameraCalibration
import com.pulso.app.sensor.ObservationEnvelope
import com.pulso.app.sensor.NavigationCandidateObservation
import com.pulso.app.sensor.NavigationObservation
import com.pulso.app.sensor.PulsoSensorSource
import com.pulso.app.sensor.PhoneTelemetryObservation
import com.pulso.app.sensor.RobotObservation
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.SensorMode
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.hypot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext

/**
 * Physical ARCore 1.54 source. The exposed [surfaceView] must be attached to the Activity view tree;
 * it owns the GL thread on which Session.update and CPU/depth acquisition occur.
 */
class AndroidRealSource(
    private val activity: Activity,
    private val confirmedTorchState: () -> Boolean?,
) : PulsoSensorSource, DefaultLifecycleObserver {
    override val mode = SensorMode.ANDROID_REAL
    private val telemetry = RealTelemetry(activity)
    private val occupancyMap = SparseOccupancyMap()
    private val latestSceneRef = AtomicReference<MetaViewScene?>(null)
    private val latestFrameRef = AtomicReference<SensorFrame?>(null)
    private val perceptionCandidatesRef = AtomicReference<PerceptionCandidateLease?>(null)
    private val capturedViews = CapturedViewStore(RECENT_FRAME_LIMIT)
    private val _observations = MutableSharedFlow<SensorFrame>(
        replay = 1,
        extraBufferCapacity = 2,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    private val _metaViewScenes = MutableSharedFlow<String>(
        replay = 1,
        extraBufferCapacity = 2,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    private val _status = MutableStateFlow("STOPPED")
    private var session: Session? = null
    private var started = false
    private var installRequested = false
    private var hostPaused = false
    private var depthEnabled = false
    private var lastProcessedTimestampNs = 0L
    private var lastTracking = TrackingState.STOPPED
    private var trackingEpoch = 0L
    private var previousPose: RealPose2d? = null
    private var thermalPaused = false

    val surfaceView: GLSurfaceView = GLSurfaceView(activity).apply {
        setEGLContextClientVersion(2)
        preserveEGLContextOnPause = true
        setRenderer(
            ArCameraRenderer(
                sessionProvider = { session },
                displayRotationProvider = ::displayRotation,
                onFrame = ::onArFrame,
                onFailure = ::onRendererFailure,
            )
        )
        renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
    }
    override val observations: Flow<SensorFrame> = _observations.asSharedFlow()
    val metaViewScenes: Flow<String> = _metaViewScenes.asSharedFlow()
    val status: StateFlow<String> = _status

    init {
        if (activity is LifecycleOwner) activity.lifecycle.addObserver(this)
    }

    fun latestMetaViewSceneJson(): String? = latestSceneRef.get()?.json

    fun metaViewSceneJson(capturedMonotonicNs: Long): String? = capturedViews.exact(capturedMonotonicNs)?.sceneJson

    fun latestNavigation(): NavigationObservation? {
        val base = latestSceneRef.get()?.navigation ?: return null
        val frame = latestFrameRef.get() ?: return base
        return mergePerceptionNavigation(
            base,
            perceptionCandidatesRef.get(),
            frame.envelope.trackingEpoch,
            SystemClock.elapsedRealtimeNanos(),
        )
    }

    fun updatePerceptionCandidates(
        candidates: List<NavigationCandidateObservation>,
        navigationRevision: Long,
        trackingEpoch: Long,
        capturedMonotonicNs: Long,
    ) {
        if (candidates.isEmpty()) {
            perceptionCandidatesRef.set(null)
            return
        }
        val current = latestSceneRef.get()?.navigation ?: return
        val frame = latestFrameRef.get() ?: return
        if (current.navigationRevision != navigationRevision || frame.envelope.trackingEpoch != trackingEpoch) return
        perceptionCandidatesRef.set(
            PerceptionCandidateLease(
                navigationRevision,
                trackingEpoch,
                capturedMonotonicNs + PERCEPTION_CANDIDATE_TTL_NS,
                candidates,
            )
        )
    }

    fun latestImuSample(): ImuSample? = telemetry.imu()

    fun isThermallyPaused(): Boolean = thermalPaused

    fun latestFrameCaptureNs(): Long = latestFrameRef.get()?.envelope?.capturedMonotonicNs ?: -1L

    /** Returns only the exact bytes authorized by a request_view capture timestamp. */
    fun latestViewBytes(viewKind: String, capturedMonotonicNs: Long): ByteArray? {
        return capturedViews.exact(capturedMonotonicNs)?.bytes(viewKind)
    }

    override suspend fun start() = withContext(Dispatchers.Main.immediate) {
        if (started) return@withContext
        check(ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            "CAMERA permission is required before AndroidRealSource.start()."
        }
        val install = ArCoreApk.getInstance().requestInstall(activity, !installRequested)
        if (install == ArCoreApk.InstallStatus.INSTALL_REQUESTED) {
            installRequested = true
            _status.value = "ARCORE_INSTALL_REQUESTED"
            error("ARCore installation requested; retry start() after the Activity resumes.")
        }
        val activeSession = session ?: Session(activity)
        val config = activeSession.config.apply {
            focusMode = Config.FocusMode.AUTO
            updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
            if (activeSession.isDepthModeSupported(Config.DepthMode.AUTOMATIC)) {
                depthMode = Config.DepthMode.AUTOMATIC
            }
        }
        activeSession.configure(config)
        session = activeSession
        depthEnabled = config.depthMode == Config.DepthMode.AUTOMATIC
        telemetry.start()
        started = true
        val hostResumed = (activity as? LifecycleOwner)?.lifecycle?.currentState?.isAtLeast(Lifecycle.State.RESUMED) != false
        hostPaused = !hostResumed
        if (hostResumed) {
            activeSession.resume()
            surfaceView.onResume()
            _status.value = runningStatus()
        } else {
            _status.value = "WAITING_HOST_RESUME"
        }
    }

    override suspend fun stop() = withContext(Dispatchers.Main.immediate) {
        if (!started) return@withContext
        if (!hostPaused) {
            surfaceView.onPause()
            runCatching { session?.pause() }
        }
        telemetry.close()
        started = false
        hostPaused = false
        _status.value = "STOPPED"
    }

    override fun close() {
        if (activity is LifecycleOwner) activity.lifecycle.removeObserver(this)
        if (started && !hostPaused) surfaceView.onPause()
        runCatching { session?.close() }
        session = null
        telemetry.close()
        started = false
    }

    override fun onPause(owner: LifecycleOwner) {
        if (!started || hostPaused) return
        surfaceView.onPause()
        runCatching { session?.pause() }
        hostPaused = true
        _status.value = "HOST_PAUSED"
    }

    override fun onResume(owner: LifecycleOwner) {
        if (!started || !hostPaused) return
        val resumed = runCatching { session?.resume() }.isSuccess
        if (!resumed) {
            _status.value = "HOST_RESUME_FAILED"
            return
        }
        surfaceView.onResume()
        hostPaused = false
        _status.value = runningStatus()
    }

    override fun onDestroy(owner: LifecycleOwner) {
        close()
    }

    private fun onArFrame(frame: Frame) {
        if (!started || frame.timestamp <= 0L) return
        val camera = frame.camera
        val currentTracking = camera.trackingState
        if (currentTracking != lastTracking) {
            if (currentTracking == TrackingState.TRACKING) trackingEpoch += 1
            lastTracking = currentTracking
        }
        if (currentTracking != TrackingState.TRACKING) {
            _status.value = "TRACKING_${currentTracking.name}:${camera.trackingFailureReason.name}"
            return
        }
        if (frame.timestamp - lastProcessedTimestampNs < FRAME_INTERVAL_NS) return
        lastProcessedTimestampNs = frame.timestamp
        val battery = telemetry.batteryFraction() ?: return
        val temperatureC = telemetry.batteryTemperatureC()
        val imu = telemetry.imu()
        if (temperatureC != null && temperatureC >= THERMAL_STOP_C) thermalPaused = true
        if (thermalPaused && (temperatureC == null || temperatureC > THERMAL_RESUME_C)) {
            _status.value = "THERMAL_STOP:${temperatureC?.let { "%.1f".format(it) } ?: "?"}C"
            return
        }
        thermalPaused = false
        val torch = confirmedTorchState()
        val capturedMonotonicNs = SystemClock.elapsedRealtimeNanos()
        val pose = cameraPose(camera, capturedMonotonicNs)
        val depth = acquireDepth(frame, camera)
        val map = occupancyMap.integrateDepth(pose, camera.displayOrientedPose.ty(), depth.pointsInMap)
        val scene = MetaViewSceneBuilder.build(map, pose, depth, trackingEpoch)
        val frameNavigation = mergePerceptionNavigation(
            scene.navigation,
            perceptionCandidatesRef.get(),
            trackingEpoch,
            capturedMonotonicNs,
        )
        val rgb = acquireRgb(frame)
        val motion = motionState(previousPose, pose)
        previousPose = pose
        latestSceneRef.set(scene)
        _metaViewScenes.tryEmit(scene.json)
        val sensorFrame = SensorFrame(
                envelope = ObservationEnvelope(
                    observationId = "REAL-$capturedMonotonicNs",
                    source = SensorMode.ANDROID_REAL,
                    capturedMonotonicNs = capturedMonotonicNs,
                    frameId = "arcore_world",
                    trackingState = "TRACKING",
                    trackingQuality = 1f,
                    trackingEpoch = trackingEpoch,
                    artifactUris = buildMap {
                        put("META_VIEW_SCENE", "pulso://metaview-scene/${map.sequence}")
                        if (torch == null) put("TORCH_STATUS", "pulso://capability/torch/unconfirmed")
                    },
                ),
                robot = RobotObservation(
                    x = pose.x,
                    y = pose.y,
                    headingDeg = pose.headingDeg,
                    poseConfidence = 1f,
                    motionState = motion,
                    batteryFraction = battery,
                    flashlightOn = torch ?: false,
                    frontRangeM = depth.frontRangeM,
                ),
                navigation = frameNavigation,
                metaViewJpeg = RealImageEncoding.metaViewJpeg(scene, pose),
                egoRgbJpeg = rgb.evidenceJpeg,
                cameraCalibration = cameraCalibration(camera),
                phoneTelemetry = PhoneTelemetryObservation(
                    imuCapturedMonotonicNs = imu?.capturedMonotonicNs,
                    accelerationMps2 = imu?.accelerationMps2,
                    angularVelocityRadps = imu?.angularVelocityRadps,
                    batteryTemperatureC = temperatureC,
                ),
                depthSamples = depth.imageSamples,
                operatorRgbJpeg = rgb.operatorJpeg,
            )
        latestFrameRef.set(sensorFrame)
        capturedViews.put(sensorFrame, scene)
        _observations.tryEmit(sensorFrame)
        _status.value = when {
            torch == null -> "TRACKING_TORCH_UNCONFIRMED"
            depth.frontRangeM == null -> "TRACKING_NO_CURRENT_DEPTH"
            else -> "TRACKING_DEPTH"
        }
    }

    private fun onRendererFailure(failure: Throwable) {
        val detail = failure.message?.replace(':', '_')?.take(96).orEmpty()
        _status.value = buildString {
            append("RENDER_ERROR:")
            append(failure::class.java.simpleName)
            if (detail.isNotEmpty()) append(":$detail")
        }
    }

    private fun cameraPose(camera: Camera, timestampNs: Long): RealPose2d {
        val arPose = camera.displayOrientedPose
        val forward = FloatArray(3)
        arPose.getTransformedAxis(2, -1f, forward, 0)
        val mapForwardX = forward[0]
        val mapForwardY = -forward[2]
        return RealPose2d(
            x = arPose.tx(),
            y = -arPose.tz(),
            headingDeg = Math.toDegrees(kotlin.math.atan2(mapForwardY.toDouble(), mapForwardX.toDouble())).toFloat(),
            capturedMonotonicNs = timestampNs,
        )
    }

    private fun displayRotation(): Int = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        activity.display?.rotation ?: Surface.ROTATION_0
    } else {
        @Suppress("DEPRECATION")
        activity.windowManager.defaultDisplay.rotation
    }

    private fun acquireDepth(frame: Frame, camera: Camera): DepthMeasurement = try {
        frame.acquireDepthImage16Bits().use { DepthEvidence.measure(it, camera) }
    } catch (_: NotYetAvailableException) {
        DepthMeasurement(null, emptyList())
    } catch (_: RuntimeException) {
        DepthMeasurement(null, emptyList())
    }

    private fun acquireRgb(frame: Frame): EncodedRgb = try {
        frame.acquireCameraImage().use { image ->
            EncodedRgb(
                evidenceJpeg = RealImageEncoding.cameraJpeg(image),
                operatorJpeg = RealImageEncoding.operatorPreviewJpeg(image),
            )
        }
    } catch (_: NotYetAvailableException) {
        EncodedRgb()
    } catch (_: RuntimeException) {
        EncodedRgb()
    }

    private fun cameraCalibration(camera: Camera): CameraCalibration? = runCatching {
        val intrinsics = camera.imageIntrinsics
        val dimensions = intrinsics.imageDimensions
        val focal = intrinsics.focalLength
        val principal = intrinsics.principalPoint
        CameraCalibration(dimensions[0], dimensions[1], focal[0], focal[1], principal[0], principal[1])
    }.getOrNull()

    private fun motionState(previous: RealPose2d?, current: RealPose2d): String {
        previous ?: return "STOPPED"
        val elapsedSeconds = (current.capturedMonotonicNs - previous.capturedMonotonicNs) / 1_000_000_000f
        if (elapsedSeconds <= 0f) return "STOPPED"
        return if (hypot(current.x - previous.x, current.y - previous.y) / elapsedSeconds > MOVING_THRESHOLD_MPS) {
            "MOVING"
        } else {
            "STOPPED"
        }
    }

    private fun runningStatus(): String = if (depthEnabled) "RUNNING_DEPTH" else "RUNNING_NO_DEPTH"

    private companion object {
        const val FRAME_INTERVAL_NS = 100_000_000L
        const val MOVING_THRESHOLD_MPS = 0.03f
        const val RECENT_FRAME_LIMIT = 8
        const val THERMAL_STOP_C = 42f
        const val THERMAL_RESUME_C = 39f
        const val PERCEPTION_CANDIDATE_TTL_NS = 15_000_000_000L
    }
}

private data class EncodedRgb(
    val evidenceJpeg: ByteArray? = null,
    val operatorJpeg: ByteArray? = null,
)

internal data class PerceptionCandidateLease(
    val navigationRevision: Long,
    val trackingEpoch: Long,
    val validUntilMonotonicNs: Long,
    val candidates: List<NavigationCandidateObservation>,
)

internal fun mergePerceptionNavigation(
    base: NavigationObservation,
    lease: PerceptionCandidateLease?,
    trackingEpoch: Long,
    nowMonotonicNs: Long,
): NavigationObservation {
    if (lease == null || lease.navigationRevision != base.navigationRevision ||
        lease.trackingEpoch != trackingEpoch || nowMonotonicNs > lease.validUntilMonotonicNs
    ) return base
    return base.copy(
        validUntilMonotonicNs = minOf(base.validUntilMonotonicNs, lease.validUntilMonotonicNs),
        candidates = base.candidates.filterNot {
            it.type == "TARGET" && it.id.startsWith("PERSON_")
        } + lease.candidates,
    )
}

internal data class ExactCapturedView(
    val capturedMonotonicNs: Long,
    val sceneJson: String,
    private val egoRgbJpeg: ByteArray?,
    private val metaViewJpeg: ByteArray?,
) {
    fun bytes(viewKind: String): ByteArray? = when (viewKind) {
        "TARGET_VIEW", "CANDIDATE_VIEW", "EGO_RGB" -> egoRgbJpeg
        else -> metaViewJpeg
    }
}

/** Atomically indexes the image and MetaView scene produced by the same ARCore capture. */
internal class CapturedViewStore(private val capacity: Int) {
    private val entries = LinkedHashMap<Long, ExactCapturedView>()

    fun put(frame: SensorFrame, scene: MetaViewScene) {
        val capturedNs = frame.envelope.capturedMonotonicNs
        require(scene.map.capturedMonotonicNs == capturedNs) { "Frame and MetaView capture timestamps differ." }
        val artifact = ExactCapturedView(capturedNs, scene.json, frame.egoRgbJpeg, frame.metaViewJpeg)
        synchronized(entries) {
            entries[capturedNs] = artifact
            while (entries.size > capacity) entries.remove(entries.keys.first())
        }
    }

    fun exact(capturedMonotonicNs: Long): ExactCapturedView? = synchronized(entries) {
        entries[capturedMonotonicNs]
    }
}
