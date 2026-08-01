package com.pulso.app.sensor.real

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageFormat
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.YuvImage
import android.media.Image
import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlin.math.min

internal object RealImageEncoding {
    fun cameraJpeg(image: Image, quality: Int = 78): ByteArray? {
        if (image.format != ImageFormat.YUV_420_888 || image.planes.size < 3) return null
        val nv21 = yuv420ToNv21(image)
        return ByteArrayOutputStream().use { output ->
            val encoded = YuvImage(nv21, ImageFormat.NV21, image.width, image.height, null)
                .compressToJpeg(Rect(0, 0, image.width, image.height), quality, output)
            if (encoded) output.toByteArray() else null
        }
    }

    /**
     * Small operator-only preview. It samples the camera YUV planes directly,
     * avoiding a full JPEG decode/resize cycle and leaving cognition evidence untouched.
     */
    fun operatorPreviewJpeg(
        image: Image,
        maxWidth: Int = OPERATOR_MAX_WIDTH,
        maxHeight: Int = OPERATOR_MAX_HEIGHT,
        quality: Int = OPERATOR_JPEG_QUALITY,
    ): ByteArray? {
        if (image.format != ImageFormat.YUV_420_888 || image.planes.size < 3) return null
        val (width, height) = fittedEvenSize(image.width, image.height, maxWidth, maxHeight)
        val nv21 = downsampleYuv420ToNv21(image, width, height)
        return ByteArrayOutputStream().use { output ->
            val encoded = YuvImage(nv21, ImageFormat.NV21, width, height, null)
                .compressToJpeg(Rect(0, 0, width, height), quality, output)
            if (encoded) output.toByteArray() else null
        }
    }

    fun metaViewJpeg(scene: MetaViewScene, pose: RealPose2d): ByteArray {
        val bitmap = Bitmap.createBitmap(META_SIZE, META_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.rgb(8, 15, 18))
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        fun screenX(worldX: Float) = META_SIZE / 2f + (worldX - pose.x) * PIXELS_PER_METER
        fun screenY(worldY: Float) = META_SIZE / 2f - (worldY - pose.y) * PIXELS_PER_METER
        val cellPixels = max(1f, scene.map.cellSizeM * PIXELS_PER_METER)
        scene.map.cells.forEach { cell ->
            paint.color = if (cell.state == CellState.OCCUPIED) Color.rgb(255, 90, 72) else Color.rgb(41, 89, 96)
            val x = screenX((cell.x + 0.5f) * scene.map.cellSizeM)
            val y = screenY((cell.y + 0.5f) * scene.map.cellSizeM)
            canvas.drawRect(x - cellPixels / 2, y - cellPixels / 2, x + cellPixels / 2, y + cellPixels / 2, paint)
        }
        paint.color = Color.rgb(255, 206, 84)
        scene.map.frontiers.forEach { cell ->
            canvas.drawCircle(
                screenX((cell.x + 0.5f) * scene.map.cellSizeM),
                screenY((cell.y + 0.5f) * scene.map.cellSizeM),
                3f,
                paint,
            )
        }
        paint.color = Color.WHITE
        canvas.drawCircle(META_SIZE / 2f, META_SIZE / 2f, 6f, paint)
        val output = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 82, output)
        bitmap.recycle()
        return output.toByteArray()
    }

    private fun yuv420ToNv21(image: Image): ByteArray {
        val width = image.width
        val height = image.height
        val output = ByteArray(width * height * 3 / 2)
        copyPlane(image.planes[0], width, height, output, 0, 1)
        val chromaOffset = width * height
        copyPlane(image.planes[2], width / 2, height / 2, output, chromaOffset, 2)
        copyPlane(image.planes[1], width / 2, height / 2, output, chromaOffset + 1, 2)
        return output
    }

    private fun fittedEvenSize(
        sourceWidth: Int,
        sourceHeight: Int,
        maxWidth: Int,
        maxHeight: Int,
    ): Pair<Int, Int> {
        val scale = min(1f, min(maxWidth.toFloat() / sourceWidth, maxHeight.toFloat() / sourceHeight))
        val width = max(2, (sourceWidth * scale).toInt() and -2)
        val height = max(2, (sourceHeight * scale).toInt() and -2)
        return width to height
    }

    private fun downsampleYuv420ToNv21(image: Image, width: Int, height: Int): ByteArray {
        val output = ByteArray(width * height * 3 / 2)
        samplePlane(
            plane = image.planes[0],
            sourceWidth = image.width,
            sourceHeight = image.height,
            outputWidth = width,
            outputHeight = height,
            destination = output,
            destinationOffset = 0,
            destinationStride = 1,
        )
        val chromaOffset = width * height
        samplePlane(
            plane = image.planes[2],
            sourceWidth = image.width / 2,
            sourceHeight = image.height / 2,
            outputWidth = width / 2,
            outputHeight = height / 2,
            destination = output,
            destinationOffset = chromaOffset,
            destinationStride = 2,
        )
        samplePlane(
            plane = image.planes[1],
            sourceWidth = image.width / 2,
            sourceHeight = image.height / 2,
            outputWidth = width / 2,
            outputHeight = height / 2,
            destination = output,
            destinationOffset = chromaOffset + 1,
            destinationStride = 2,
        )
        return output
    }

    private fun samplePlane(
        plane: Image.Plane,
        sourceWidth: Int,
        sourceHeight: Int,
        outputWidth: Int,
        outputHeight: Int,
        destination: ByteArray,
        destinationOffset: Int,
        destinationStride: Int,
    ) {
        val buffer = plane.buffer.duplicate()
        var outputIndex = destinationOffset
        for (row in 0 until outputHeight) {
            val sourceRow = row * sourceHeight / outputHeight
            for (column in 0 until outputWidth) {
                val sourceColumn = column * sourceWidth / outputWidth
                val index = sourceRow * plane.rowStride + sourceColumn * plane.pixelStride
                if (index < buffer.limit() && outputIndex < destination.size) {
                    destination[outputIndex] = buffer.get(index)
                }
                outputIndex += destinationStride
            }
        }
    }

    private fun copyPlane(
        plane: Image.Plane,
        width: Int,
        height: Int,
        destination: ByteArray,
        destinationOffset: Int,
        destinationStride: Int,
    ) {
        val buffer = plane.buffer.duplicate()
        var outputIndex = destinationOffset
        for (row in 0 until height) {
            for (column in 0 until width) {
                val index = row * plane.rowStride + column * plane.pixelStride
                if (index < buffer.limit() && outputIndex < destination.size) destination[outputIndex] = buffer.get(index)
                outputIndex += destinationStride
            }
        }
    }

    private const val META_SIZE = 384
    private const val PIXELS_PER_METER = 35f
    private const val OPERATOR_MAX_WIDTH = 640
    private const val OPERATOR_MAX_HEIGHT = 480
    private const val OPERATOR_JPEG_QUALITY = 62
}
