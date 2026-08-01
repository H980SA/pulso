package com.pulso.app.sensor.real

import kotlin.math.atan2
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

data class RealPose2d(
    val x: Float,
    val y: Float,
    val headingDeg: Float,
    val capturedMonotonicNs: Long,
)

data class SparsePoint(val x: Float, val y: Float, val z: Float)

enum class CellState { FREE, OCCUPIED }

data class OccupancyCell(val x: Int, val y: Int, val state: CellState, val evidence: Float)

data class LocalMapSnapshot(
    val sequence: Long,
    val capturedMonotonicNs: Long,
    val cellSizeM: Float,
    val points: List<SparsePoint>,
    val cells: List<OccupancyCell>,
    val frontiers: List<OccupancyCell>,
)

/** A bounded local map. Every occupied/free cell is backed by reprojected ARCore DEPTH16 rays. */
class SparseOccupancyMap(
    private val cellSizeM: Float = 0.25f,
    private val radiusM: Float = 8f,
    private val maxPoints: Int = 1_200,
) {
    private data class Evidence(var score: Float, var seenNs: Long)

    private val cells = mutableMapOf<Pair<Int, Int>, Evidence>()
    private var sequence = 0L
    private var committedTopology: SemanticTopology? = null
    private var pendingTopology: SemanticTopology? = null
    private var pendingTopologyFrames = 0

    private data class SemanticTopology(
        val occupied: Set<Pair<Int, Int>>,
        val frontiers: Set<Pair<Int, Int>>,
    )

    fun integrateDepth(
        pose: RealPose2d,
        cameraHeightM: Float,
        depthPoints: List<DepthPoint>,
    ): LocalMapSnapshot {
        val observed = ArrayList<SparsePoint>(min(maxPoints, depthPoints.size))
        for (point in depthPoints) {
            if (observed.size >= maxPoints) break
            val vertical = point.z - cameraHeightM
            if (!point.x.isFinite() || !point.y.isFinite() || !vertical.isFinite()) continue
            if (hypot(point.x - pose.x, point.y - pose.y) > radiusM) continue
            observed += SparsePoint(point.x, point.y, vertical)
            traceEvidence(
                pose.x,
                pose.y,
                point.x,
                point.y,
                vertical in MIN_OBSTACLE_HEIGHT_M..MAX_OBSTACLE_HEIGHT_M,
                pose.capturedMonotonicNs,
            )
        }
        evictOutside(pose)
        return snapshot(pose.capturedMonotonicNs, observed)
    }

    private fun traceEvidence(
        originX: Float,
        originY: Float,
        hitX: Float,
        hitY: Float,
        occupiedEndpoint: Boolean,
        nowNs: Long,
    ) {
        val dx = hitX - originX
        val dy = hitY - originY
        val distance = hypot(dx, dy)
        val steps = max(1, floor(distance / cellSizeM).toInt())
        for (step in 0 until steps) {
            val fraction = step.toFloat() / steps
            updateCell(originX + dx * fraction, originY + dy * fraction, -FREE_DELTA, nowNs)
        }
        if (occupiedEndpoint) updateCell(hitX, hitY, OCCUPIED_DELTA, nowNs)
    }

    private fun updateCell(x: Float, y: Float, delta: Float, nowNs: Long) {
        val key = gridKey(x, y)
        val existing = cells.getOrPut(key) { Evidence(0f, nowNs) }
        existing.score = (existing.score + delta).coerceIn(-MAX_EVIDENCE, MAX_EVIDENCE)
        existing.seenNs = nowNs
    }

    private fun evictOutside(pose: RealPose2d) {
        val radiusCells = radiusM / cellSizeM
        val poseKey = gridKey(pose.x, pose.y)
        cells.entries.removeAll { (key, evidence) ->
            hypot((key.first - poseKey.first).toFloat(), (key.second - poseKey.second).toFloat()) > radiusCells ||
                pose.capturedMonotonicNs - evidence.seenNs > MAX_CELL_AGE_NS
        }
    }

    private fun snapshot(nowNs: Long, points: List<SparsePoint>): LocalMapSnapshot {
        val classified = cells.mapNotNull { (key, value) ->
            when {
                value.score >= OCCUPIED_THRESHOLD -> OccupancyCell(key.first, key.second, CellState.OCCUPIED, value.score)
                value.score <= FREE_THRESHOLD -> OccupancyCell(key.first, key.second, CellState.FREE, -value.score)
                else -> null
            }
        }
        val states = classified.associateBy { it.x to it.y }
        val frontiers = classified.filter { cell ->
            cell.state == CellState.FREE && NEIGHBORS.any { (dx, dy) -> (cell.x + dx to cell.y + dy) !in states }
        }.sortedByDescending { it.evidence }.take(MAX_FRONTIERS)
        val topology = SemanticTopology(
            occupied = classified.filter { it.state == CellState.OCCUPIED }.map(::semanticBucket).toSet(),
            frontiers = frontiers.map(::semanticBucket).toSet(),
        )
        val committed = committedTopology
        val unsafeObstacleAdded = committed != null && (topology.occupied - committed.occupied).isNotEmpty()
        val significantCandidateChange = committed != null &&
            (topology.frontiers subtract committed.frontiers).size +
            (committed.frontiers subtract topology.frontiers).size >= SIGNIFICANT_FRONTIER_DELTA
        when {
            committed == null || unsafeObstacleAdded -> commit(topology)
            topology == committed -> {
                pendingTopology = null
                pendingTopologyFrames = 0
            }
            significantCandidateChange -> {
                if (pendingTopology == topology) pendingTopologyFrames += 1 else {
                    pendingTopology = topology
                    pendingTopologyFrames = 1
                }
                if (pendingTopologyFrames >= TOPOLOGY_DEBOUNCE_FRAMES) commit(topology)
            }
            // Sub-cell jitter and sparse ray dropout are not semantic topology changes.
            else -> Unit
        }
        return LocalMapSnapshot(sequence, nowNs, cellSizeM, points, classified, frontiers)
    }

    private fun commit(topology: SemanticTopology) {
        if (topology != committedTopology) {
            sequence += 1
            committedTopology = topology
        }
        pendingTopology = null
        pendingTopologyFrames = 0
    }

    private fun semanticBucket(cell: OccupancyCell): Pair<Int, Int> {
        val centerX = (cell.x + 0.5f) * cellSizeM
        val centerY = (cell.y + 0.5f) * cellSizeM
        return (centerX / SEMANTIC_CELL_M).roundToInt() to (centerY / SEMANTIC_CELL_M).roundToInt()
    }

    private fun gridKey(x: Float, y: Float): Pair<Int, Int> =
        floor(x / cellSizeM).toInt() to floor(y / cellSizeM).toInt()

    companion object {
        private const val MIN_OBSTACLE_HEIGHT_M = -0.2f
        private const val MAX_OBSTACLE_HEIGHT_M = 0.55f
        private const val FREE_DELTA = 0.18f
        private const val OCCUPIED_DELTA = 0.65f
        private const val MAX_EVIDENCE = 4f
        private const val FREE_THRESHOLD = -0.3f
        private const val OCCUPIED_THRESHOLD = 0.45f
        private const val MAX_CELL_AGE_NS = 30_000_000_000L
        private const val MAX_FRONTIERS = 12
        private const val SEMANTIC_CELL_M = 0.5f
        private const val SIGNIFICANT_FRONTIER_DELTA = 3
        private const val TOPOLOGY_DEBOUNCE_FRAMES = 3
        private val NEIGHBORS = listOf(-1 to 0, 1 to 0, 0 to -1, 0 to 1)
    }
}

internal fun normalizeDegrees(value: Float): Float {
    var result = value % 360f
    if (result > 180f) result -= 360f
    if (result < -180f) result += 360f
    return result
}

internal fun bearingDeg(fromX: Float, fromY: Float, toX: Float, toY: Float): Float =
    Math.toDegrees(atan2((toY - fromY).toDouble(), (toX - fromX).toDouble())).toFloat()
