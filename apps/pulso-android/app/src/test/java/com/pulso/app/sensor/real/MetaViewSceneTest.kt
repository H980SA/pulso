package com.pulso.app.sensor.real

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MetaViewSceneTest {
    @Test
    fun emitsCanonicalMissionControlSceneWithoutInventingDepthPoints() {
        val map = LocalMapSnapshot(
            sequence = 7,
            capturedMonotonicNs = 2_000_000_000L,
            cellSizeM = 0.25f,
            points = listOf(SparsePoint(1f, 2f, 0f)),
            cells = listOf(OccupancyCell(4, 8, CellState.FREE, 1f)),
            frontiers = listOf(OccupancyCell(4, 8, CellState.FREE, 1f)),
        )

        val scene = MetaViewSceneBuilder.build(
            map,
            RealPose2d(0f, 0f, 90f, map.capturedMonotonicNs),
            depth = DepthMeasurement(frontRangeM = null, pointsInMap = emptyList()),
            trackingEpoch = 3,
        )
        val root = Json.parseToJsonElement(scene.json).jsonObject

        assertEquals("pulso.metaview-scene.v1", root["contract_version"]?.jsonPrimitive?.content)
        assertEquals("map", root["frame_id"]?.jsonPrimitive?.content)
        assertTrue(root["map"]?.jsonObject?.get("free_points_m")?.jsonArray?.isNotEmpty() == true)
        assertEquals(3, root["robot"]?.jsonObject?.get("position_m")?.jsonArray?.size)
        assertTrue(root["depth"]?.jsonObject?.get("points_m")?.jsonArray?.isEmpty() == true)
        assertEquals(0, root["depth"]?.jsonObject?.get("sample_count")?.jsonPrimitive?.content?.toInt())
        assertEquals(4, root["bounds_m"]?.jsonArray?.size)
        assertFalse("sparse_points" in root)
        assertFalse("navigation_candidates" in root)
        assertTrue(scene.navigation.candidates.any { it.type == "FRONTIER" })
        assertTrue(scene.navigation.candidates.any { it.type == "VIEWPOINT" })
    }
}
