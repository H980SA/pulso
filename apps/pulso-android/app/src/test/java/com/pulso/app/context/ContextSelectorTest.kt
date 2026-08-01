package com.pulso.app.context

import com.pulso.app.demo.demoWorld
import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.VisualView
import com.pulso.app.domain.projectSensorWorld
import com.pulso.app.sensor.ObservationEnvelope
import com.pulso.app.sensor.RobotObservation
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.SensorMode
import com.pulso.app.sensor.real.CellState
import com.pulso.app.sensor.real.DepthMeasurement
import com.pulso.app.sensor.real.LocalMapSnapshot
import com.pulso.app.sensor.real.MetaViewSceneBuilder
import com.pulso.app.sensor.real.OccupancyCell
import com.pulso.app.sensor.real.RealPose2d
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ContextSelectorTest {
    private val selector = ContextSelector()
    private val cognitive = CognitiveState("question", "plan", null, null)
    private val checkpoint = MissionCheckpoint("M-001", "G-007", emptyList(), emptyList(), emptyList())

    @Test
    fun sensorMapUpdatesDoNotInvalidateNavigationCandidates() {
        val original = demoWorld()
        val integratedDepth = original.copy(sensorMapSeq = original.sensorMapSeq + 1)

        val packet = selector.select(integratedDepth, DecisionNeed.CHOOSE_ROUTE, cognitive, checkpoint)

        assertEquals(listOf("VP-17", "VP-18", "FR-021"), packet.candidates.map { it.id.value })
    }

    @Test
    fun materialNavigationRevisionInvalidatesOldCandidates() {
        val original = demoWorld()
        val topologyChanged = original.copy(navigationRevision = original.navigationRevision + 1)

        val packet = selector.select(topologyChanged, DecisionNeed.CHOOSE_ROUTE, cognitive, checkpoint)

        assertTrue(packet.candidates.isEmpty())
    }

    @Test
    fun visualEvidenceIsDemandDriven() {
        val world = demoWorld()
        val requested = VisualView(
            artifactId = "metaview_NAV27",
            kind = "META_VIEW",
            navigationRevision = world.navigationRevision,
            requestActionId = "A-REQUEST-7",
            jpegBytes = byteArrayOf(1, 2, 3),
        )

        assertNull(selector.select(world, DecisionNeed.CHOOSE_ROUTE, cognitive, checkpoint).visualView)
        assertEquals(
            requested,
            selector.select(
                world,
                DecisionNeed.CHOOSE_ROUTE,
                cognitive,
                checkpoint,
                requested,
            ).visualView,
        )
        assertNull(selector.select(world, DecisionNeed.MONITOR, cognitive, checkpoint).visualView)
    }

    @Test
    fun visualWithoutSuccessfulRequestViewAuthorizationIsNeverAttached() {
        val world = demoWorld()
        val unrequested = VisualView(
            artifactId = "metaview-unrequested",
            kind = "META_VIEW",
            navigationRevision = world.navigationRevision,
            jpegBytes = byteArrayOf(1, 2, 3),
        )

        assertNull(
            selector.select(
                world,
                DecisionNeed.CHOOSE_ROUTE,
                cognitive,
                checkpoint,
                unrequested,
            ).visualView
        )
    }

    @Test
    fun expiredCandidatesAreRemovedFromThePacket() {
        val world = demoWorld()
        val expired = world.copy(monotonicNowMs = world.monotonicNowMs + 30_000)

        assertTrue(selector.select(expired, DecisionNeed.CHOOSE_ROUTE, cognitive, checkpoint).candidates.isEmpty())
    }

    @Test
    fun physicalMetaViewLeaseSurvivesWorldProjectionAndSelection() {
        val capturedNs = 9_000_000_000L
        val pose = RealPose2d(0f, 0f, 0f, capturedNs)
        val frontier = OccupancyCell(2, 0, CellState.FREE, 1f)
        val map = LocalMapSnapshot(14, capturedNs, 0.25f, emptyList(), listOf(frontier), listOf(frontier))
        val scene = MetaViewSceneBuilder.build(map, pose, DepthMeasurement(null, emptyList()), trackingEpoch = 7)
        val frame = SensorFrame(
            envelope = ObservationEnvelope(
                observationId = "REAL-$capturedNs",
                source = SensorMode.ANDROID_REAL,
                capturedMonotonicNs = capturedNs,
                frameId = "arcore_world",
                trackingState = "TRACKING",
                trackingQuality = 1f,
                trackingEpoch = 7,
                artifactUris = emptyMap(),
            ),
            robot = RobotObservation(0f, 0f, 0f, 1f, "STOPPED", 0.8f, false, 1f),
            navigation = scene.navigation,
            metaViewJpeg = byteArrayOf(1),
            egoRgbJpeg = byteArrayOf(2),
            cameraCalibration = null,
        )
        val world = projectSensorWorld(demoWorld(), frame, missionStartNs = capturedNs)

        val packet = selector.select(world, DecisionNeed.CHOOSE_ROUTE, cognitive, checkpoint)

        assertTrue(packet.candidates.isNotEmpty())
        assertTrue(packet.candidates.all { it.targetRevision != null && it.capability.length >= 16 })
    }
}
