package com.pulso.app.perception

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.SystemClock
import com.pulso.app.sensor.CameraCalibration
import java.nio.FloatBuffer
import kotlin.math.atan2
import kotlin.math.max
import kotlin.math.min

data class PersonDetection(
    val confidence: Float,
    val leftNorm: Float,
    val topNorm: Float,
    val rightNorm: Float,
    val bottomNorm: Float,
    val bearingDeg: Float,
    val inferenceLatencyMs: Long,
    val visibleKeypoints: Int,
)

internal data class PoseCandidate(
    val confidence: Float,
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
    val visibleKeypoints: Int,
)

/**
 * Asynchronous saliency sensor backed by YOLO11n-pose. Pose supervision is
 * materially more robust than a generic COCO box detector for prone and
 * partially occluded people. Its output remains a clue: Gemma must inspect the
 * RGB evidence before claiming a survivor, injury, entrapment, or consciousness.
 */
class PersonDetector(context: Context) : AutoCloseable {
    private val environment = OrtEnvironment.getEnvironment()
    private val sessionOptions = OrtSession.SessionOptions().apply {
        setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        setIntraOpNumThreads(4)
    }
    private val session: OrtSession
    private val inputName: String

    init {
        val modelBytes = context.applicationContext.assets.open(MODEL_ASSET).use { it.readBytes() }
        session = environment.createSession(modelBytes, sessionOptions)
        inputName = session.inputNames.first()
    }

    fun detect(
        jpegBytes: ByteArray,
        calibration: CameraCalibration?,
    ): List<PersonDetection> {
        val startedMs = SystemClock.elapsedRealtime()
        val decoded = BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.size)
            ?: throw IllegalArgumentException("RGB JPEG could not be decoded")
        val bitmap = if (decoded.config == Bitmap.Config.ARGB_8888) {
            decoded
        } else {
            decoded.copy(Bitmap.Config.ARGB_8888, false).also { decoded.recycle() }
        }
        return try {
            val letterbox = prepareInput(bitmap)
            val shape = longArrayOf(1, 3, INPUT_SIZE.toLong(), INPUT_SIZE.toLong())
            OnnxTensor.createTensor(environment, FloatBuffer.wrap(letterbox.chw), shape).use { tensor ->
                session.run(mapOf(inputName to tensor)).use { output ->
                    @Suppress("UNCHECKED_CAST")
                    val channels = (output[0].value as Array<Array<FloatArray>>)[0]
                    val candidates = decodeCandidates(
                        channels = channels,
                        originalWidth = bitmap.width,
                        originalHeight = bitmap.height,
                        scale = letterbox.scale,
                        padX = letterbox.padX,
                        padY = letterbox.padY,
                    )
                    val latencyMs = SystemClock.elapsedRealtime() - startedMs
                    nonMaximumSuppression(candidates, IOU_THRESHOLD, MAX_RESULTS).map { candidate ->
                        val centerX = (candidate.left + candidate.right) * 0.5f
                        PersonDetection(
                            confidence = candidate.confidence,
                            leftNorm = (candidate.left / bitmap.width).coerceIn(0f, 1f),
                            topNorm = (candidate.top / bitmap.height).coerceIn(0f, 1f),
                            rightNorm = (candidate.right / bitmap.width).coerceIn(0f, 1f),
                            bottomNorm = (candidate.bottom / bitmap.height).coerceIn(0f, 1f),
                            bearingDeg = bearingDegrees(centerX, bitmap.width, calibration),
                            inferenceLatencyMs = latencyMs,
                            visibleKeypoints = candidate.visibleKeypoints,
                        )
                    }
                }
            }
        } finally {
            bitmap.recycle()
        }
    }

    override fun close() {
        session.close()
        sessionOptions.close()
    }

    private fun prepareInput(bitmap: Bitmap): LetterboxInput {
        val scale = min(INPUT_SIZE.toFloat() / bitmap.width, INPUT_SIZE.toFloat() / bitmap.height)
        val scaledWidth = max(1, (bitmap.width * scale).toInt())
        val scaledHeight = max(1, (bitmap.height * scale).toInt())
        val padX = (INPUT_SIZE - scaledWidth) * 0.5f
        val padY = (INPUT_SIZE - scaledHeight) * 0.5f
        val resized = Bitmap.createScaledBitmap(bitmap, scaledWidth, scaledHeight, true)
        val pixels = IntArray(scaledWidth * scaledHeight)
        resized.getPixels(pixels, 0, scaledWidth, 0, 0, scaledWidth, scaledHeight)
        if (resized !== bitmap) resized.recycle()

        val planeSize = INPUT_SIZE * INPUT_SIZE
        val padding = LETTERBOX_COLOR / 255f
        val chw = FloatArray(planeSize * 3) { padding }
        val left = padX.toInt()
        val top = padY.toInt()
        pixels.forEachIndexed { index, color ->
            val sourceY = index / scaledWidth
            val sourceX = index - sourceY * scaledWidth
            val target = (top + sourceY) * INPUT_SIZE + left + sourceX
            chw[target] = ((color shr 16) and 0xFF) / 255f
            chw[planeSize + target] = ((color shr 8) and 0xFF) / 255f
            chw[planeSize * 2 + target] = (color and 0xFF) / 255f
        }
        return LetterboxInput(chw, scale, padX, padY)
    }

    private fun decodeCandidates(
        channels: Array<FloatArray>,
        originalWidth: Int,
        originalHeight: Int,
        scale: Float,
        padX: Float,
        padY: Float,
    ): List<PoseCandidate> {
        require(channels.size >= POSE_CHANNELS) {
            "Unexpected YOLO pose output: ${channels.size} channels"
        }
        val anchors = channels[0].size
        return buildList {
            for (anchor in 0 until anchors) {
                val confidence = channels[4][anchor]
                if (confidence < SCORE_THRESHOLD) continue
                val centerX = channels[0][anchor]
                val centerY = channels[1][anchor]
                val width = channels[2][anchor]
                val height = channels[3][anchor]
                val left = ((centerX - width * 0.5f - padX) / scale)
                    .coerceIn(0f, originalWidth.toFloat())
                val top = ((centerY - height * 0.5f - padY) / scale)
                    .coerceIn(0f, originalHeight.toFloat())
                val right = ((centerX + width * 0.5f - padX) / scale)
                    .coerceIn(0f, originalWidth.toFloat())
                val bottom = ((centerY + height * 0.5f - padY) / scale)
                    .coerceIn(0f, originalHeight.toFloat())
                if (right - left < 4f || bottom - top < 4f) continue
                var visibleKeypoints = 0
                for (keypoint in 0 until KEYPOINT_COUNT) {
                    if (channels[5 + keypoint * 3 + 2][anchor] >= KEYPOINT_THRESHOLD) {
                        visibleKeypoints += 1
                    }
                }
                add(
                    PoseCandidate(
                        confidence = confidence.coerceIn(0f, 1f),
                        left = left,
                        top = top,
                        right = right,
                        bottom = bottom,
                        visibleKeypoints = visibleKeypoints,
                    )
                )
            }
        }
    }

    private data class LetterboxInput(
        val chw: FloatArray,
        val scale: Float,
        val padX: Float,
        val padY: Float,
    )

    companion object {
        const val MODEL_ASSET = "models/yolo11n_pose.onnx"
        const val MODEL_ID = "yolo11n-pose-onnx"
        private const val INPUT_SIZE = 640
        private const val POSE_CHANNELS = 56
        private const val KEYPOINT_COUNT = 17
        private const val LETTERBOX_COLOR = 114
        private const val SCORE_THRESHOLD = 0.18f
        private const val KEYPOINT_THRESHOLD = 0.25f
        private const val IOU_THRESHOLD = 0.45f
        private const val MAX_RESULTS = 4
    }
}

internal fun nonMaximumSuppression(
    candidates: List<PoseCandidate>,
    iouThreshold: Float,
    maxResults: Int,
): List<PoseCandidate> {
    val remaining = candidates.sortedByDescending { it.confidence }.toMutableList()
    val selected = mutableListOf<PoseCandidate>()
    while (remaining.isNotEmpty() && selected.size < maxResults) {
        val best = remaining.removeAt(0)
        selected += best
        remaining.removeAll { intersectionOverUnion(best, it) > iouThreshold }
    }
    return selected
}

internal fun intersectionOverUnion(first: PoseCandidate, second: PoseCandidate): Float {
    val intersectionWidth = max(0f, min(first.right, second.right) - max(first.left, second.left))
    val intersectionHeight = max(0f, min(first.bottom, second.bottom) - max(first.top, second.top))
    val intersection = intersectionWidth * intersectionHeight
    val firstArea = max(0f, first.right - first.left) * max(0f, first.bottom - first.top)
    val secondArea = max(0f, second.right - second.left) * max(0f, second.bottom - second.top)
    val union = firstArea + secondArea - intersection
    return if (union <= 0f) 0f else intersection / union
}

internal fun bearingDegrees(
    pixelX: Float,
    imageWidth: Int,
    calibration: CameraCalibration?,
): Float {
    val scaledCx: Float
    val scaledFx: Float
    if (calibration != null && calibration.fx > 0f && calibration.width > 0) {
        val scale = imageWidth.toFloat() / calibration.width.toFloat()
        scaledCx = calibration.cx * scale
        scaledFx = calibration.fx * scale
    } else {
        scaledCx = imageWidth * 0.5f
        scaledFx = imageWidth * 0.62f
    }
    val safeX = min(max(pixelX, 0f), imageWidth.toFloat())
    return Math.toDegrees(atan2((safeX - scaledCx).toDouble(), scaledFx.toDouble())).toFloat()
}
