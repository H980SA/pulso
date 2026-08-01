package com.pulso.app.sensor.real

import android.media.Image
import com.google.ar.core.Camera
import com.pulso.app.sensor.DepthSampleObservation
import kotlin.math.ceil
import kotlin.math.sqrt

data class DepthPoint(val x: Float, val y: Float, val z: Float)

data class DepthMeasurement(
    val frontRangeM: Float?,
    val pointsInMap: List<DepthPoint>,
    val imageSamples: List<DepthSampleObservation> = emptyList(),
)

/** DEPTH16 extraction and reprojection. ARCore feature points never enter this depth payload. */
internal object DepthEvidence {
    fun measure(image: Image, camera: Camera): DepthMeasurement {
        if (image.width <= 0 || image.height <= 0 || image.planes.isEmpty()) return DepthMeasurement(null, emptyList())
        val front = frontRangeMeters(image)
        val intrinsics = camera.textureIntrinsics
        val sourceDimensions = intrinsics.imageDimensions
        if (sourceDimensions[0] <= 0 || sourceDimensions[1] <= 0) return DepthMeasurement(front, emptyList())
        val focal = intrinsics.focalLength
        val principal = intrinsics.principalPoint
        val scaleX = image.width.toFloat() / sourceDimensions[0]
        val scaleY = image.height.toFloat() / sourceDimensions[1]
        val fx = focal[0] * scaleX
        val fy = focal[1] * scaleY
        val cx = principal[0] * scaleX
        val cy = principal[1] * scaleY
        if (fx <= 0f || fy <= 0f) return DepthMeasurement(front, emptyList())
        val sampleStride = ceil(sqrt(image.width * image.height / MAX_DEPTH_POINTS.toDouble())).toInt().coerceAtLeast(1)
        val pose = camera.pose
        val points = ArrayList<DepthPoint>(MAX_DEPTH_POINTS)
        val imageSamples = ArrayList<DepthSampleObservation>(MAX_DEPTH_POINTS)
        var y = sampleStride / 2
        while (y < image.height && points.size < MAX_DEPTH_POINTS) {
            var x = sampleStride / 2
            while (x < image.width && points.size < MAX_DEPTH_POINTS) {
                val millimeters = depthMillimeters(image, x, y)
                if (millimeters in MIN_VALID_MM..MAX_VALID_MM) {
                    val depthM = millimeters / 1_000f
                    val local = floatArrayOf(
                        (x - cx) * depthM / fx,
                        -(y - cy) * depthM / fy,
                        -depthM,
                    )
                    val world = FloatArray(3)
                    pose.transformPoint(local, 0, world, 0)
                    points += DepthPoint(world[0], -world[2], world[1])
                    imageSamples += DepthSampleObservation(
                        uNorm = (x + 0.5f) / image.width,
                        vNorm = (y + 0.5f) / image.height,
                        rangeM = depthM,
                    )
                }
                x += sampleStride
            }
            y += sampleStride
        }
        return DepthMeasurement(front, points, imageSamples)
    }

    private fun frontRangeMeters(image: Image): Float? {
        val halfWidth = (image.width * ROI_HALF_FRACTION).toInt().coerceAtLeast(1)
        val halfHeight = (image.height * ROI_HALF_FRACTION).toInt().coerceAtLeast(1)
        val centerX = image.width / 2
        val centerY = image.height / 2
        val valuesMm = ArrayList<Int>()
        var y = centerY - halfHeight
        while (y <= centerY + halfHeight) {
            var x = centerX - halfWidth
            while (x <= centerX + halfWidth) {
                val millimeters = depthMillimeters(image, x, y)
                if (millimeters in MIN_VALID_MM..MAX_VALID_MM) valuesMm += millimeters
                x += ROI_SAMPLE_STRIDE
            }
            y += ROI_SAMPLE_STRIDE
        }
        if (valuesMm.size < MIN_SAMPLE_COUNT) return null
        valuesMm.sort()
        return valuesMm[(valuesMm.lastIndex * NEAR_PERCENTILE).toInt()] / 1_000f
    }

    private fun depthMillimeters(image: Image, x: Int, y: Int): Int {
        if (x !in 0 until image.width || y !in 0 until image.height) return 0
        val plane = image.planes[0]
        val buffer = plane.buffer
        val offset = y * plane.rowStride + x * plane.pixelStride
        if (offset < 0 || offset + 1 >= buffer.limit()) return 0
        return (buffer.get(offset).toInt() and 0xff) or ((buffer.get(offset + 1).toInt() and 0xff) shl 8)
    }

    private const val MAX_DEPTH_POINTS = 1_600
    private const val ROI_HALF_FRACTION = 0.12f
    private const val ROI_SAMPLE_STRIDE = 2
    private const val MIN_SAMPLE_COUNT = 8
    private const val MIN_VALID_MM = 100
    private const val MAX_VALID_MM = 20_000
    private const val NEAR_PERCENTILE = 0.2f
}
