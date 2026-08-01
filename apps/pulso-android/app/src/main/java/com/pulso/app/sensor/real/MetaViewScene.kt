package com.pulso.app.sensor.real

import com.pulso.app.sensor.NavigationCandidateObservation
import com.pulso.app.sensor.NavigationObservation
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.security.SecureRandom
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

data class MetaViewScene(
    val json: String,
    val navigation: NavigationObservation,
    val map: LocalMapSnapshot,
)

/** Builds the exact operator contract consumed by Mission Control's parseMetaviewScene. */
internal object MetaViewSceneBuilder {
    private val decisionLeases = NavigationDecisionLeases()

    fun build(
        map: LocalMapSnapshot,
        pose: RealPose2d,
        depth: DepthMeasurement,
        trackingEpoch: Long,
    ): MetaViewScene {
        val validUntilNs = map.capturedMonotonicNs + NAVIGATION_TTL_NS
        val frontierSeeds = map.frontiers.map { cell ->
            candidate(
                "FRONTIER",
                spatialId("F", cell, map.cellSizeM),
                cell,
                map,
                pose,
                "",
            )
        }.distinctBy { it.type to it.id }
        val viewpointSeeds = map.frontiers.map { cell ->
            candidate(
                "VIEWPOINT",
                spatialId("V", cell, map.cellSizeM),
                cell,
                map,
                pose,
                "",
            )
        }.distinctBy { it.type to it.id }.take(MAX_VIEWPOINTS)
        val leased = decisionLeases.revalidate(frontierSeeds + viewpointSeeds, map, trackingEpoch)
        val frontiers = leased.filter { it.type == "FRONTIER" }
        val viewpoints = leased.filter { it.type == "VIEWPOINT" }
        val navigation = NavigationObservation(
            capturedMonotonicNs = map.capturedMonotonicNs,
            sensorMapSeq = map.sequence,
            navigationRevision = map.sequence,
            validUntilMonotonicNs = validUntilNs,
            candidates = frontiers + viewpoints,
        )
        val free = map.cells.filter { it.state == CellState.FREE }
        val occupied = map.cells.filter { it.state == CellState.OCCUPIED }
        val grid = gridShape(map, pose)
        val routes = (frontiers.take(3) + viewpoints.take(3)).take(6)
        val bounds = sceneBounds(map, pose, depth.pointsInMap, routes)
        val root = buildJsonObject {
            put("contract_version", "pulso.metaview-scene.v1")
            put("captured_monotonic_ns", map.capturedMonotonicNs)
            put("frame_id", "map")
            put("sensor_map_seq", map.sequence)
            put("navigation_revision", map.sequence)
            put("map", buildJsonObject {
                put("resolution_m", map.cellSizeM)
                put("origin_m", floatsJson(listOf(grid.originX, grid.originY)))
                put("width", grid.width)
                put("height", grid.height)
                put("free_points_m", cellCenters(free, map.cellSizeM))
                put("occupied_points_m", cellCenters(occupied, map.cellSizeM))
                put("known_cells", map.cells.size)
                put("unknown_cells", (grid.width * grid.height - map.cells.size).coerceAtLeast(0))
            })
            put("robot", buildJsonObject {
                put("position_m", floatsJson(listOf(pose.x, pose.y, 0f)))
                put("heading_deg", pose.headingDeg)
                depth.frontRangeM?.let { put("front_range_m", it) }
                put("tracking_epoch", trackingEpoch)
            })
            put("depth", buildJsonObject {
                put("source", "arcore/depth16")
                put("frame_id", "map")
                put("points_m", buildJsonArray {
                    depth.pointsInMap.forEach { point -> add(floatsJson(listOf(point.x, point.y, point.z))) }
                })
                put("sample_count", depth.pointsInMap.size)
            })
            put("scan_footprint_m", buildJsonArray { })
            put("routes", buildJsonArray {
                routes.forEachIndexed { index, route -> add(routeJson(route, pose, index)) }
            })
            put("bounds_m", floatsJson(bounds))
        }
        return MetaViewScene(root.toString(), navigation, map)
    }

    private fun candidate(
        type: String,
        id: String,
        cell: OccupancyCell,
        map: LocalMapSnapshot,
        pose: RealPose2d,
        capability: String,
    ): NavigationCandidateObservation {
        val x = (cell.x + 0.5f) * map.cellSizeM
        val y = (cell.y + 0.5f) * map.cellSizeM
        val occupiedNeighbors = map.cells.count { other ->
            other.state == CellState.OCCUPIED && kotlin.math.abs(other.x - cell.x) <= 1 &&
                kotlin.math.abs(other.y - cell.y) <= 1
        }
        return NavigationCandidateObservation(
            type = type,
            id = id,
            label = if (type == "FRONTIER") "Frontera observada" else "Punto de vista derivado",
            purpose = if (type == "FRONTIER") "Expandir el mapa local" else "Inspeccionar la frontera observada",
            x = x,
            y = y,
            pathLengthM = hypot(x - pose.x, y - pose.y),
            risk = (occupiedNeighbors / 8f).coerceIn(0f, 1f),
            informationGain = unknownNeighborFraction(cell, map),
            capability = capability,
        )
    }

    private fun routeJson(route: NavigationCandidateObservation, pose: RealPose2d, index: Int) = buildJsonObject {
        put("id", route.id); put("type", route.type); put("label", ('A'.code + index).toChar().toString())
        put("selected", false)
        put("position_m", floatsJson(listOf(route.x, route.y, 0f)))
        put("path_m", buildJsonArray {
            add(floatsJson(listOf(pose.x, pose.y, 0f))); add(floatsJson(listOf(route.x, route.y, 0f)))
        })
        put("risk", route.risk); put("information_gain", route.informationGain)
    }

    private fun cellCenters(cells: List<OccupancyCell>, size: Float) = buildJsonArray {
        cells.forEach { add(floatsJson(listOf((it.x + 0.5f) * size, (it.y + 0.5f) * size))) }
    }

    private data class GridShape(val originX: Float, val originY: Float, val width: Int, val height: Int)

    private fun gridShape(map: LocalMapSnapshot, pose: RealPose2d): GridShape {
        if (map.cells.isEmpty()) return GridShape(pose.x, pose.y, 0, 0)
        val minX = map.cells.minOf { it.x }; val maxX = map.cells.maxOf { it.x }
        val minY = map.cells.minOf { it.y }; val maxY = map.cells.maxOf { it.y }
        return GridShape(minX * map.cellSizeM, minY * map.cellSizeM, maxX - minX + 1, maxY - minY + 1)
    }

    private fun sceneBounds(
        map: LocalMapSnapshot,
        pose: RealPose2d,
        depth: List<DepthPoint>,
        routes: List<NavigationCandidateObservation>,
    ): List<Float> {
        val xs = mutableListOf(pose.x); val ys = mutableListOf(pose.y)
        map.cells.forEach { xs += (it.x + 0.5f) * map.cellSizeM; ys += (it.y + 0.5f) * map.cellSizeM }
        depth.forEach { xs += it.x; ys += it.y }
        routes.forEach { xs += it.x; ys += it.y }
        return listOf(xs.min(), ys.min(), xs.max(), ys.max())
    }

    private fun unknownNeighborFraction(cell: OccupancyCell, map: LocalMapSnapshot): Float {
        val known = map.cells.asSequence().map { it.x to it.y }.toHashSet()
        val offsets = (-1..1).flatMap { dx -> (-1..1).map { dy -> dx to dy } }.filterNot { it == 0 to 0 }
        return offsets.count { (dx, dy) -> (cell.x + dx to cell.y + dy) !in known } / offsets.size.toFloat()
    }

    private fun spatialId(prefix: String, cell: OccupancyCell, cellSizeM: Float): String {
        val x = ((cell.x + 0.5f) * cellSizeM / CANDIDATE_BUCKET_M).roundToInt()
        val y = ((cell.y + 0.5f) * cellSizeM / CANDIDATE_BUCKET_M).roundToInt()
        return "$prefix-$x-$y"
    }

    private fun floatsJson(values: List<Float>) = JsonArray(values.map(::JsonPrimitive))

    // Covers the measured on-device E4B decision cycle while resolveTarget still revalidates
    // the latest geometry and grant immediately before every targeted physical action.
    internal const val NAVIGATION_TTL_NS = 15_000_000_000L
    private const val CANDIDATE_BUCKET_M = 0.5f
    private const val MAX_VIEWPOINTS = 6
}

/**
 * Keeps a decision grant while the same spatial candidate is freshly re-observed. A VIO epoch,
 * local occupied geometry, or material risk change rotates the grant and target revision.
 */
internal class NavigationDecisionLeases {
    private data class Lease(
        val type: String,
        val stableId: String,
        var x: Float,
        var y: Float,
        var risk: Float,
        var obstacleSignature: Set<Pair<Int, Int>>,
        var trackingEpoch: Long,
        var targetRevision: Long,
        var grant: String,
    )

    private val leases = mutableMapOf<Pair<String, String>, Lease>()

    fun revalidate(
        measured: List<NavigationCandidateObservation>,
        map: LocalMapSnapshot,
        trackingEpoch: Long,
    ): List<NavigationCandidateObservation> {
        val used = mutableSetOf<Pair<String, String>>()
        return measured.map { candidate ->
            val directKey = candidate.type to candidate.id
            val nearest = leases.entries.asSequence()
                .filter { it.key !in used && it.value.type == candidate.type }
                .map { it to hypot(candidate.x - it.value.x, candidate.y - it.value.y) }
                .filter { it.second <= CANDIDATE_MATCH_RADIUS_M }
                .minByOrNull { it.second }
                ?.first
            val entry = leases[directKey]?.let { directKey to it } ?: nearest?.let { it.key to it.value }
            val signature = localObstacleSignature(candidate, map)
            val lease = if (entry == null) {
                newLease(candidate, signature, trackingEpoch)
            } else {
                val current = entry.second
                val unsafeChanged = current.trackingEpoch != trackingEpoch ||
                    current.obstacleSignature != signature ||
                    abs(current.risk - candidate.risk) >= MATERIAL_RISK_DELTA
                if (unsafeChanged) rotate(current, trackingEpoch)
                current.x = candidate.x
                current.y = candidate.y
                current.risk = candidate.risk
                current.obstacleSignature = signature
                if (entry.first != directKey) {
                    leases.remove(entry.first)
                    leases[candidate.type to current.stableId] = current
                }
                current
            }
            val key = lease.type to lease.stableId
            leases.putIfAbsent(key, lease)
            used += key
            candidate.copy(id = lease.stableId, capability = lease.grant, targetRevision = lease.targetRevision)
        }
    }

    private fun newLease(
        candidate: NavigationCandidateObservation,
        signature: Set<Pair<Int, Int>>,
        trackingEpoch: Long,
    ): Lease {
        val revision = 1L
        return Lease(
            candidate.type,
            candidate.id,
            candidate.x,
            candidate.y,
            candidate.risk,
            signature,
            trackingEpoch,
            revision,
            NavigationGrantIssuer.issue(revision, trackingEpoch, candidate.type, candidate.id),
        )
    }

    private fun rotate(lease: Lease, trackingEpoch: Long) {
        lease.targetRevision += 1
        lease.trackingEpoch = trackingEpoch
        lease.grant = NavigationGrantIssuer.issue(
            lease.targetRevision,
            trackingEpoch,
            lease.type,
            lease.stableId,
        )
    }

    private fun localObstacleSignature(
        candidate: NavigationCandidateObservation,
        map: LocalMapSnapshot,
    ): Set<Pair<Int, Int>> = map.cells.asSequence()
        .filter { it.state == CellState.OCCUPIED }
        .map { cell ->
            val x = (cell.x + 0.5f) * map.cellSizeM
            val y = (cell.y + 0.5f) * map.cellSizeM
            Triple(x, y, (x / OBSTACLE_BUCKET_M).roundToInt() to (y / OBSTACLE_BUCKET_M).roundToInt())
        }
        .filter { (x, y) -> hypot(x - candidate.x, y - candidate.y) <= LOCAL_OBSTACLE_RADIUS_M }
        .map { it.third }
        .toSet()

    private companion object {
        const val CANDIDATE_MATCH_RADIUS_M = 0.65f
        const val LOCAL_OBSTACLE_RADIUS_M = 0.8f
        const val OBSTACLE_BUCKET_M = 0.5f
        const val MATERIAL_RISK_DELTA = 0.2f
    }
}

/**
 * Issues process-local, opaque grants. Equivalent measured topology keeps the same grant long
 * enough for an on-device decision; a topology revision or VIO relocalization rotates it.
 */
internal object NavigationGrantIssuer {
    private val secret = ByteArray(32).also(SecureRandom()::nextBytes)

    fun issue(navigationRevision: Long, trackingEpoch: Long, type: String, id: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update(secret)
        digest.update(ByteBuffer.allocate(Long.SIZE_BYTES * 2).apply {
            putLong(navigationRevision)
            putLong(trackingEpoch)
        }.array())
        digest.update(type.toByteArray(Charsets.UTF_8))
        digest.update(0.toByte())
        digest.update(id.toByteArray(Charsets.UTF_8))
        return "grant_" + digest.digest().take(16).joinToString("") { "%02x".format(it) }
    }
}
