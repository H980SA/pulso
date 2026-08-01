package com.pulso.app.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pulso.app.domain.Candidate
import com.pulso.app.runtime.ModelStatus
import com.pulso.app.sensor.SensorMode
import kotlin.math.roundToInt

@Composable
internal fun PulsoStatusHeader(state: PulsoUiState) {
    Row(
        Modifier.fillMaxWidth().height(42.dp),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("PULSO", color = PulsoInk, fontSize = 22.sp, fontWeight = FontWeight.Black)
        Text(
            if (state.sensorMode == SensorMode.ANDROID_REAL) "CAMPO" else "SIMULACIÓN",
            color = PulsoOrange,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.sp,
        )
        Text("·", color = PulsoInk)
        Text(state.sensorMode.name, color = PulsoInk, fontFamily = FontFamily.Monospace, fontSize = 9.sp)
        StatusValue(
            if (state.hasLiveObservation) "LIVE" else "WAITING",
            if (state.hasLiveObservation) PulsoGreen else PulsoFaint,
        )
        Spacer(Modifier.weight(1f))
        StatusPair("GEMMA 4 E4B", state.model.status.name, modelTone(state.model.status))
        Divider()
        StatusPair(
            "VIO",
            if (state.hasLiveObservation) {
                "${state.world.robot.trackingState} ${(state.world.robot.trackingQuality * 100).roundToInt()}%"
            } else "—",
            if (state.world.robot.trackingQuality >= 0.65f) PulsoGreen else PulsoFaint,
        )
        Divider()
        StatusPair("MODELO", "YOLO11N-POSE", PulsoInk)
        StatusPair("MIC", state.acousticStatus, if (state.acousticStatus.startsWith("ALERTA")) PulsoOrange else PulsoInk)
        StatusPair("ROVER", state.roverStatus, if (state.roverArmed) PulsoOrange else PulsoInk)
        Divider()
        StatusPair("MISIÓN", formatDuration(state.world.missionElapsedMs), PulsoInk)
    }
}

@Composable
private fun StatusPair(label: String, value: String, tone: Color) {
    Column {
        Text(label, color = PulsoFaint, fontSize = 7.sp, letterSpacing = 1.sp)
        Text(value, color = tone, fontSize = 9.sp, fontFamily = FontFamily.Monospace, maxLines = 1)
    }
}

@Composable
private fun StatusValue(value: String, tone: Color) {
    Text(
        value,
        color = tone,
        fontFamily = FontFamily.Monospace,
        fontSize = 8.sp,
        modifier = Modifier.border(1.dp, tone.copy(alpha = 0.45f)).padding(horizontal = 5.dp, vertical = 2.dp),
    )
}

@Composable
private fun Divider() = Box(Modifier.width(1.dp).height(24.dp).background(PulsoBorder))

@Composable
internal fun BrainConsole(state: PulsoUiState, modifier: Modifier = Modifier) {
    ConsolePanel("CEREBRO  ·  decisiones observables", modifier) {
        ConsoleLabel("MISIÓN / GOAL")
        Text("${state.world.mission.id} · ${state.world.mission.title}", color = PulsoInk, fontSize = 9.sp)
        Spacer(Modifier.height(8.dp))
        Text(
            "${state.world.activeGoal.id} · ${state.world.activeGoal.title}",
            color = PulsoOrange,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
        )
        Spacer(Modifier.height(10.dp))
        ConsoleLabel("PREGUNTA ACTIVA")
        Text(state.cognitive.currentQuestion, color = PulsoInk, fontSize = 11.sp, lineHeight = 15.sp)
        Spacer(Modifier.height(10.dp))
        ConsoleLabel("DECISIÓN ACTUAL")
        Box(
            Modifier.fillMaxWidth().border(1.dp, PulsoBorder).padding(8.dp),
        ) {
            Column {
                Text(
                    state.lastAgentResponse,
                    color = if (state.model.status == ModelStatus.ERROR) PulsoRed else PulsoInk,
                    fontSize = 9.sp,
                    lineHeight = 13.sp,
                    maxLines = 5,
                    overflow = TextOverflow.Ellipsis,
                )
                state.model.lastLoopLatencyMs?.let {
                    Text("VERIFICADO · ${it} ms", color = PulsoGreen, fontSize = 7.sp)
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        ConsoleLabel("EVENTOS PÚBLICOS · no chain-of-thought")
        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(state.trace.takeLast(8).reversed()) { trace ->
                Row(Modifier.fillMaxWidth()) {
                    Text("○", color = traceTone(trace.category), fontSize = 9.sp)
                    Spacer(Modifier.width(6.dp))
                    Text(
                        trace.category,
                        color = traceTone(trace.category),
                        fontSize = 7.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.width(52.dp),
                    )
                    Text(
                        trace.text,
                        color = PulsoMuted,
                        fontSize = 7.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
internal fun WorldPacketConsole(state: PulsoUiState, modifier: Modifier = Modifier) {
    ConsolePanel("WORLDPACKET  ·  ${state.decisionNeed}", modifier) {
        ConsoleLabel("CONTEXTO ENTREGADO A GEMMA")
        Text(
            "world_seq ${state.packet.worldSeq} · ${state.packet.candidates.size} candidatos · " +
                if (state.packet.visualView == null) "sin imagen" else state.packet.visualView.kind,
            color = PulsoOrange,
            fontFamily = FontFamily.Monospace,
            fontSize = 8.sp,
        )
        Spacer(Modifier.height(8.dp))
        if (state.packet.candidates.isEmpty()) {
            EmptyPacket(state)
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                items(state.packet.candidates.take(6)) { candidate ->
                    val index = state.packet.candidates.indexOf(candidate)
                    CandidateEvidence(candidate, index, if (index == 0) state.egoRgbJpeg else null)
                }
            }
        }
    }
}

@Composable
private fun CandidateEvidence(candidate: Candidate, index: Int, jpeg: ByteArray?) {
    val tone = candidateColor(index)
    val bitmap = remember(jpeg) {
        jpeg?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
    }
    Row(
        Modifier.fillMaxWidth().border(1.dp, if (index == 0) tone else PulsoBorder).padding(8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            ('A'.code + index).toChar().toString(),
            color = tone,
            fontSize = 21.sp,
            fontWeight = FontWeight.Black,
        )
        Column(Modifier.weight(1f)) {
            Text(
                "${candidate.id.kind}: ${candidate.id.value}",
                color = tone,
                fontFamily = FontFamily.Monospace,
                fontSize = 8.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(candidate.label, color = PulsoInk, fontSize = 8.sp, maxLines = 2)
            Text(
                "${candidate.pathLengthM}m · risk ${(candidate.risk * 100).roundToInt()} · info ${(candidate.informationGain * 100).roundToInt()}",
                color = PulsoMuted,
                fontSize = 7.sp,
            )
        }
        if (bitmap != null) {
            Image(
                bitmap = bitmap,
                contentDescription = "Vista sensorial fresca para ${candidate.id.value}",
                contentScale = ContentScale.Crop,
                modifier = Modifier.width(92.dp).height(52.dp).border(1.dp, PulsoBorder),
            )
        } else {
            Text("SIN IMAGEN", color = PulsoFaint, fontSize = 7.sp, modifier = Modifier.width(56.dp))
        }
    }
}

@Composable
private fun EmptyPacket(state: PulsoUiState) {
    Box(Modifier.fillMaxWidth().border(1.dp, PulsoBorder).padding(12.dp)) {
        Text(
            if (state.hasLiveObservation) "El planificador aún no publicó candidatos válidos."
            else "Sin fuente sensorial. Gemma no recibe candidatos ni imágenes.",
            color = PulsoMuted,
            fontSize = 8.sp,
        )
    }
}

@Composable
private fun ConsolePanel(title: String, modifier: Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.background(PulsoPanel).border(1.dp, PulsoBorder).padding(12.dp),
        verticalArrangement = Arrangement.Top,
    ) {
        Text(title, color = PulsoInk, fontSize = 10.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.4.sp)
        Spacer(Modifier.height(12.dp))
        content()
    }
}

@Composable
private fun ConsoleLabel(text: String) {
    Text(text, color = PulsoFaint, fontSize = 7.sp, letterSpacing = 0.8.sp, fontWeight = FontWeight.Medium)
}

private fun modelTone(status: ModelStatus) = when (status) {
    ModelStatus.READY -> PulsoGreen
    ModelStatus.THINKING, ModelStatus.LOADING -> PulsoOrange
    ModelStatus.ERROR, ModelStatus.NOT_INSTALLED -> PulsoRed
    ModelStatus.COLD -> PulsoFaint
}

private fun traceTone(category: String) = when (category) {
    "TOOL", "ACTION" -> PulsoOrange
    "RESULT", "LATENCY" -> PulsoGreen
    "ERROR", "BLOCKED", "STOP" -> PulsoRed
    else -> PulsoInk
}

private fun formatDuration(ms: Long): String {
    val totalSeconds = ms / 1_000
    return "%02d:%02d:%02d".format(totalSeconds / 3_600, totalSeconds / 60 % 60, totalSeconds % 60)
}
