package com.pulso.app.sensor.real

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SparseOccupancyMapTest {
    @Test
    fun pointCloudProducesOnlyEvidenceBackedOccupancyAndFrontiers() {
        val map = SparseOccupancyMap(cellSizeM = 0.25f, radiusM = 4f)
        val pose = RealPose2d(0f, 0f, 90f, 1_000_000_000L)
        val points = listOf(
            DepthPoint(0f, 1f, 1f),
            DepthPoint(0.4f, 1.2f, 1f),
            DepthPoint(-0.4f, 1.2f, 1f),
            DepthPoint(Float.NaN, 2f, 1f),
        )

        val snapshot = map.integrateDepth(pose, cameraHeightM = 1f, depthPoints = points)

        assertEquals(3, snapshot.points.size)
        assertTrue(snapshot.cells.any { it.state == CellState.OCCUPIED })
        assertTrue(snapshot.cells.any { it.state == CellState.FREE })
        assertTrue(snapshot.frontiers.all { it.state == CellState.FREE })
    }

    @Test
    fun emptyPointCloudDoesNotInventCells() {
        val snapshot = SparseOccupancyMap().integrateDepth(
            RealPose2d(0f, 0f, 0f, 10L),
            cameraHeightM = 1f,
            depthPoints = emptyList(),
        )

        assertTrue(snapshot.points.isEmpty())
        assertTrue(snapshot.cells.isEmpty())
        assertTrue(snapshot.frontiers.isEmpty())
    }

    @Test
    fun equivalentDepthFramesKeepRevisionAndSpatialTargetsStableDuringDecision() {
        val map = SparseOccupancyMap(cellSizeM = 0.25f, radiusM = 4f)
        val points = listOf(
            DepthPoint(-0.5f, 1.5f, 1f),
            DepthPoint(0f, 1.5f, 1f),
            DepthPoint(0.5f, 1.5f, 1f),
        )
        fun scene(timestamp: Long): MetaViewScene {
            val pose = RealPose2d(0f, 0f, 90f, timestamp)
            val snapshot = map.integrateDepth(pose, cameraHeightM = 1f, depthPoints = points)
            return MetaViewSceneBuilder.build(snapshot, pose, DepthMeasurement(1.5f, points), trackingEpoch = 1)
        }

        scene(1_000_000_000L)
        val selectedScene = scene(1_200_000_000L)
        val selected = selectedScene.navigation.candidates.first()
        val laterScene = scene(1_400_000_000L)

        assertEquals(selectedScene.navigation.navigationRevision, laterScene.navigation.navigationRevision)
        assertTrue(laterScene.navigation.candidates.any { it.type == selected.type && it.id == selected.id })
        assertTrue(laterScene.navigation.validUntilMonotonicNs > selectedScene.navigation.validUntilMonotonicNs)
        val revalidated = laterScene.navigation.candidates.first { it.type == selected.type && it.id == selected.id }
        assertEquals(selected.capability, revalidated.capability)
        assertTrue(revalidated.capability.length >= 16)
        assertFalse(revalidated.capability.contains("MOVE_TO"))
        assertFalse(revalidated.capability.contains("LOOK_AT"))
        assertTrue(laterScene.navigation.validUntilMonotonicNs - laterScene.navigation.capturedMonotonicNs >= 15_000_000_000L)
    }

    @Test
    fun grantsAreCandidateScopedAndRotateWithSemanticRevision() {
        val first = NavigationGrantIssuer.issue(7, 2, "FRONTIER", "F-1-2")
        val same = NavigationGrantIssuer.issue(7, 2, "FRONTIER", "F-1-2")
        val otherCandidate = NavigationGrantIssuer.issue(7, 2, "FRONTIER", "F-1-3")
        val laterRevision = NavigationGrantIssuer.issue(8, 2, "FRONTIER", "F-1-2")

        assertEquals(first, same)
        assertNotEquals(first, otherCandidate)
        assertNotEquals(first, laterRevision)
        assertTrue(first.length >= 16)
    }

    @Test
    fun jitterAndSubsamplingKeepCandidateLeaseBeyondMeasuredDecisionCycle() {
        val map = SparseOccupancyMap(cellSizeM = 0.25f, radiusM = 4f)
        fun points(frame: Int): List<DepthPoint> {
            val jitter = if (frame % 2 == 0) 0.035f else -0.035f
            val all = listOf(-0.75f, -0.25f, 0.25f, 0.75f).map {
                DepthPoint(it + jitter, 1.5f - jitter, 1f)
            }
            return if (frame % 3 == 0) all.filterIndexed { index, _ -> index % 2 == 0 } else all
        }
        fun scene(frame: Int): MetaViewScene {
            val timestamp = 10_000_000_000L + frame * 200_000_000L
            val pose = RealPose2d(0f, 0f, 90f, timestamp)
            val measured = points(frame)
            return MetaViewSceneBuilder.build(
                map.integrateDepth(pose, 1f, measured),
                pose,
                DepthMeasurement(1.5f, measured),
                trackingEpoch = 41,
            )
        }

        repeat(8) { scene(it) }
        val selectedScene = scene(8)
        val selected = selectedScene.navigation.candidates.first()
        val laterScene = (9..45).map(::scene).last()
        val revalidated = laterScene.navigation.candidates.first { it.type == selected.type && it.id == selected.id }

        assertTrue(laterScene.navigation.capturedMonotonicNs - selectedScene.navigation.capturedMonotonicNs > 7_000_000_000L)
        assertEquals(selected.capability, revalidated.capability)
        assertEquals(selected.targetRevision, revalidated.targetRevision)
        assertEquals(selectedScene.navigation.navigationRevision, laterScene.navigation.navigationRevision)
    }

    @Test
    fun localObstacleMaterialRiskOrTrackingChangeRotatesLease() {
        val leases = NavigationDecisionLeases()
        val clearMap = LocalMapSnapshot(1, 1, 0.25f, emptyList(), emptyList(), emptyList())
        val candidate = candidateForLease(risk = 0.1f)
        val initial = leases.revalidate(listOf(candidate), clearMap, trackingEpoch = 1).single()

        val obstacleMap = clearMap.copy(
            capturedMonotonicNs = 2,
            cells = listOf(OccupancyCell(4, 4, CellState.OCCUPIED, 1f)),
        )
        val obstacleChanged = leases.revalidate(listOf(candidate), obstacleMap, trackingEpoch = 1).single()
        val riskChanged = leases.revalidate(listOf(candidate.copy(risk = 0.5f)), obstacleMap, trackingEpoch = 1).single()
        val trackingChanged = leases.revalidate(listOf(candidate.copy(risk = 0.5f)), obstacleMap, trackingEpoch = 2).single()

        assertNotEquals(initial.capability, obstacleChanged.capability)
        assertNotEquals(obstacleChanged.capability, riskChanged.capability)
        assertNotEquals(riskChanged.capability, trackingChanged.capability)
    }

    private fun candidateForLease(risk: Float) = com.pulso.app.sensor.NavigationCandidateObservation(
        type = "FRONTIER",
        id = "F-2-2",
        label = "Frontera",
        purpose = "Expandir",
        x = 1f,
        y = 1f,
        pathLengthM = 1.4f,
        risk = risk,
        informationGain = 0.8f,
    )
}
