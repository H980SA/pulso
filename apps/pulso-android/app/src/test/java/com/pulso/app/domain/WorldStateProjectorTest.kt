package com.pulso.app.domain

import com.pulso.app.demo.demoWorld
import com.pulso.app.perception.PersonDetection
import com.pulso.app.sensor.NavigationCandidateObservation
import com.pulso.app.sensor.NavigationObservation
import com.pulso.app.sensor.ObservationEnvelope
import com.pulso.app.sensor.RobotObservation
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.SensorMode
import com.pulso.app.sensor.DepthSampleObservation
import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.sensor.navigationPayload
import com.pulso.app.sensor.real.PerceptionCandidateLease
import com.pulso.app.sensor.real.mergePerceptionNavigation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WorldStateProjectorTest {
    @Test
    fun hilAndRealAdaptersShareTheSameWorldProjectionBoundary() {
        val frame = qaFrame()
        val projected = projectHilWorld(demoWorld(), frame, missionStartNs = 1_000_000_000L)

        assertEquals(SensorMode.GAZEBO_HIL.name, projected.source)
        assertEquals(12L, projected.navigationRevision)
        assertEquals(1, projected.candidates.size)
        assertEquals(CandidateId(CandidateKind.FRONTIER, "F_A"), projected.candidates.single().id)
        assertEquals("qa_capability_123456789", projected.candidates.single().capability)
        assertEquals(TrackingState.TRACKING, projected.robot.trackingState)
        assertEquals(0.42f, projected.robot.frontRangeM)
    }

    @Test
    fun subsequentSensorFramesDoNotOverwriteTheAgentMissionFocus() {
        val first = projectHilWorld(demoWorld(), qaFrame(), missionStartNs = 1_000_000_000L)
        val focused = first.copy(
            activeGoal = Goal("G-0999", first.mission.id, "Inspect B", "Fresh target view"),
        )
        val second = projectHilWorld(focused, qaFrame(), missionStartNs = 1_000_000_000L)

        assertEquals("G-0999", second.activeGoal.id)
        assertEquals("Inspect B", second.activeGoal.title)
    }

    @Test
    fun aPoseClueCreatesARevisionButNotASurvivorClaim() {
        val frame = qaFrame()
        val previous = projectHilWorld(demoWorld(), frame, missionStartNs = 1_000_000_000L)
        val projection = projectDetections(
            previous = previous,
            previousNeed = DecisionNeed.CHOOSE_ROUTE,
            frame = frame,
            detections = listOf(
                PersonDetection(0.78f, 0.2f, 0.3f, 0.7f, 0.9f, 14f, 83L, 11),
            ),
            previousDetectionRevision = 3,
            previousSignature = "",
        )

        assertEquals(DecisionNeed.INSPECT_TARGET, projection.decisionNeed)
        assertTrue(projection.semanticChanged)
        assertEquals("PERSON_1", projection.world.targets.single().id)
        assertTrue(projection.world.hypotheses.single().claim.contains("todavía no confirma"))
        assertEquals(1, projection.tracks.size)
        assertTrue(projection.world.candidates.none { it.id.value == "PERSON_1" })
        assertEquals(null, projection.world.targets.single().rangeM)
    }

    @Test
    fun detectionWithDepthRoiCreatesInspectableMeasuredPersonCandidate() {
        val baseFrame = qaFrame()
        val frame = baseFrame.copy(
            depthSamples = listOf(
                DepthSampleObservation(0.42f, 0.50f, 2.0f),
                DepthSampleObservation(0.48f, 0.55f, 2.1f),
                DepthSampleObservation(0.55f, 0.60f, 2.2f),
            ),
        )
        val previous = projectHilWorld(demoWorld(), frame, missionStartNs = 1_000_000_000L)
        val projection = projectDetections(
            previous,
            DecisionNeed.CHOOSE_ROUTE,
            frame,
            listOf(PersonDetection(0.78f, 0.2f, 0.3f, 0.7f, 0.9f, 14f, 83L, 11)),
            3,
            "",
        )

        val person = projection.world.candidates.single { it.id.value == "PERSON_1" }
        val packet = ContextSelector().select(
            projection.world,
            DecisionNeed.INSPECT_TARGET,
            CognitiveState("inspect", "look", null, null),
            MissionCheckpoint("M-001", "G-001", emptyList(), emptyList(), emptyList()),
        )

        assertEquals(2.1f, projection.world.targets.single().rangeM)
        assertEquals(CandidateKind.TARGET, person.id.kind)
        assertTrue(person.position.x.isFinite() && person.position.y.isFinite())
        assertEquals("PERSON_1", packet.candidates.single().id.value)
        assertTrue(person.capability.length >= 16)

        val nextCapturedNs = frame.envelope.capturedMonotonicNs + 200_000_000L
        val mergedNavigation = mergePerceptionNavigation(
            frame.navigation!!.copy(capturedMonotonicNs = nextCapturedNs),
            PerceptionCandidateLease(
                navigationRevision = projection.world.navigationRevision,
                trackingEpoch = frame.envelope.trackingEpoch,
                validUntilMonotonicNs = frame.envelope.capturedMonotonicNs + 15_000_000_000L,
                candidates = projection.navigationCandidates,
            ),
            trackingEpoch = frame.envelope.trackingEpoch,
            nowMonotonicNs = nextCapturedNs,
        )
        val nextFrame = frame.copy(
            envelope = frame.envelope.copy(
                observationId = "QA-2",
                capturedMonotonicNs = nextCapturedNs,
            ),
            navigation = mergedNavigation,
        )
        val nextWorld = projectSensorWorld(projection.world, nextFrame, 1_000_000_000L)
        val nextPacket = ContextSelector().select(
            nextWorld,
            DecisionNeed.INSPECT_TARGET,
            CognitiveState("inspect", "look", null, null),
            MissionCheckpoint("M-001", "G-001", emptyList(), emptyList(), emptyList()),
        )

        assertEquals("PERSON_1", nextPacket.candidates.single().id.value)
        assertTrue(navigationPayload(mergedNavigation).toString().contains("PERSON_1"))
    }

    private fun qaFrame(): SensorFrame = SensorFrame(
        envelope = ObservationEnvelope(
            observationId = "QA-1",
            source = SensorMode.GAZEBO_HIL,
            capturedMonotonicNs = 2_000_000_000L,
            frameId = "map",
            trackingState = "TRACKING",
            trackingQuality = 0.91f,
            trackingEpoch = 3,
            artifactUris = mapOf("POINT_CLOUD" to "ros:///pulso/phone/depth/points"),
        ),
        robot = RobotObservation(
            x = 1.0f,
            y = 2.0f,
            headingDeg = 45f,
            poseConfidence = 0.9f,
            motionState = "STOPPED",
            batteryFraction = 0.8f,
            flashlightOn = false,
            frontRangeM = 0.42f,
        ),
        navigation = NavigationObservation(
            capturedMonotonicNs = 2_000_000_000L,
            sensorMapSeq = 8,
            navigationRevision = 12,
            validUntilMonotonicNs = 4_000_000_000L,
            candidates = listOf(
                NavigationCandidateObservation(
                    type = "FRONTIER",
                    id = "F_A",
                    label = "Camino A",
                    purpose = "Expandir mapa",
                    x = 1.4f,
                    y = 2.2f,
                    pathLengthM = 0.5f,
                    risk = 0.2f,
                    informationGain = 0.8f,
                    capability = "qa_capability_123456789",
                ),
            ),
        ),
        metaViewJpeg = byteArrayOf(1),
        egoRgbJpeg = byteArrayOf(2),
        cameraCalibration = null,
    )
}
