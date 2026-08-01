package com.pulso.app.ui

import android.graphics.BitmapFactory
import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pulso.app.domain.Candidate
import com.pulso.app.domain.Vec2
import com.pulso.app.domain.WorldState
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun WorldMap(
    world: WorldState,
    selectedCandidates: List<Candidate>,
    metaViewJpeg: ByteArray?,
    modifier: Modifier = Modifier,
) {
    val liveBitmap = remember(metaViewJpeg) {
        metaViewJpeg?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
    }
    Box(
        modifier = modifier
            .background(PulsoPanel)
            .border(1.dp, PulsoBorder),
    ) {
        if (liveBitmap != null) {
            Image(
                bitmap = liveBitmap,
                contentDescription = "MetaView construida con sensores PULSO",
                contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp, vertical = 32.dp),
            )
        } else if (world.worldSeq > 0) {
            LiveVectorMap(world, selectedCandidates)
        } else {
            Text(
                "ESPERANDO MAPA SENSORIAL\nLa geometría aparecerá al recibir el primer frame válido.",
                color = PulsoMuted,
                fontFamily = FontFamily.Monospace,
                fontSize = 9.sp,
                modifier = Modifier.align(Alignment.Center),
            )
        }
        Text(
            text = "METAVIEW  ·  mapa construido en marcha",
            color = PulsoInk,
            fontSize = 10.sp,
            letterSpacing = 0.5.sp,
            modifier = Modifier.align(Alignment.TopStart).padding(14.dp),
        )
        Text(
            text = "${world.source}  ·  world_seq ${world.worldSeq}",
            color = if (world.worldSeq > 0) PulsoOrange else PulsoFaint,
            fontFamily = FontFamily.Monospace,
            fontSize = 8.sp,
            modifier = Modifier.align(Alignment.BottomEnd).padding(14.dp),
        )
    }
}

@Composable
private fun LiveVectorMap(world: WorldState, candidates: List<Candidate>) {
    Canvas(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 34.dp)) {
        fun project(point: Vec2) = Offset(
            x = ((point.x + 4.2f) / 14.5f) * size.width,
            y = size.height - ((point.y + 3.5f) / 7f) * size.height,
        )

        for (index in 0..14) {
            val x = size.width * index / 14f
            drawLine(Color(0xFFEDEAE4), Offset(x, 0f), Offset(x, size.height), 1f)
        }
        for (index in 0..7) {
            val y = size.height * index / 7f
            drawLine(Color(0xFFEDEAE4), Offset(0f, y), Offset(size.width, y), 1f)
        }
        world.obstacles.forEach { polygon ->
            if (polygon.isEmpty()) return@forEach
            val path = Path()
            polygon.forEachIndexed { index, point ->
                val projected = project(point)
                if (index == 0) path.moveTo(projected.x, projected.y)
                else path.lineTo(projected.x, projected.y)
            }
            path.close()
            drawPath(path, Color(0xFFB7B3AB).copy(alpha = 0.55f))
            drawPath(path, Color(0xFF77736C), style = Stroke(1.5f))
        }

        val robot = project(world.robot.pose.position)
        candidates.forEachIndexed { index, candidate ->
            val color = candidateColor(index)
            val target = project(candidate.position)
            val control = Offset((robot.x + target.x) / 2f, minOf(robot.y, target.y) - 20f - index * 7f)
            val route = Path().apply {
                moveTo(robot.x, robot.y)
                quadraticTo(control.x, control.y, target.x, target.y)
            }
            drawPath(route, color.copy(alpha = 0.92f), style = Stroke(width = if (index == 0) 4f else 2.4f))
            drawCircle(PulsoPanel, 11f, target)
            drawCircle(color, 9f, target)
            drawContext.canvas.nativeCanvas.drawText(
                ('A'.code + index).toChar().toString(),
                target.x - 4f,
                target.y + 5f,
                Paint().apply {
                    this.color = android.graphics.Color.WHITE
                    textSize = 13f
                    isFakeBoldText = true
                },
            )
        }

        drawCircle(PulsoGreen.copy(alpha = 0.16f), 20f, robot)
        drawCircle(PulsoGreen, 8f, robot)
        val heading = Math.toRadians(world.robot.pose.headingDeg.toDouble())
        drawLine(
            PulsoGreen,
            robot,
            Offset(robot.x + cos(heading).toFloat() * 24f, robot.y - sin(heading).toFloat() * 24f),
            3f,
        )
        world.targets.forEach { target ->
            val rangeM = target.rangeM ?: return@forEach
            val radians = Math.toRadians((world.robot.pose.headingDeg + target.bearingDeg).toDouble())
            val position = Vec2(
                world.robot.pose.position.x + cos(radians).toFloat() * rangeM,
                world.robot.pose.position.y + sin(radians).toFloat() * rangeM,
            )
            val projected = project(position)
            drawCircle(PulsoOrange.copy(alpha = 0.16f), 18f, projected)
            drawCircle(PulsoOrange, 5f, projected)
        }
    }
}

fun candidateColor(index: Int): Color = when (index % 6) {
    0 -> PulsoOrange
    1 -> PulsoMagenta
    2 -> PulsoCyan
    3 -> PulsoGreen
    4 -> PulsoYellow
    else -> Color(0xFF7A63C7)
}
