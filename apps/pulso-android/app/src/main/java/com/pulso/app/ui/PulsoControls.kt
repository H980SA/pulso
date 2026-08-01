package com.pulso.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pulso.app.runtime.ModelStatus
import com.pulso.app.sensor.SensorMode

@Composable
internal fun PulsoControls(
    state: PulsoUiState,
    onInitialize: () -> Unit,
    onConnectReal: () -> Unit,
    onConnectHil: () -> Unit,
    onAutonomy: () -> Unit,
    onRun: () -> Unit,
    onNeed: () -> Unit,
    onStop: () -> Unit,
    onClose: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ControlButton(
            symbol = "⇩",
            label = "CARGAR GEMMA",
            enabled = !state.busy && state.model.status !in setOf(ModelStatus.READY, ModelStatus.THINKING),
            onClick = onInitialize,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "▣",
            label = "CONECTAR S25",
            enabled = !state.busy && state.sensorMode != SensorMode.ANDROID_REAL,
            onClick = onConnectReal,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "◇",
            label = "CONECTAR GAZEBO",
            enabled = !state.busy && state.sensorMode != SensorMode.GAZEBO_HIL,
            onClick = onConnectHil,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "◎",
            label = if (state.autonomyEnabled) "PAUSAR AUTO" else "ACTIVAR AUTO",
            enabled = state.autonomyEnabled || (
                !state.busy && state.hasLiveObservation && state.model.status == ModelStatus.READY
            ),
            onClick = onAutonomy,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "▷",
            label = "EJECUTAR CICLO",
            enabled = !state.busy && state.hasLiveObservation && state.model.status == ModelStatus.READY,
            onClick = onRun,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "⇄",
            label = "CAMBIAR DECISIÓN",
            enabled = !state.busy && state.hasLiveObservation,
            onClick = onNeed,
            modifier = Modifier.weight(1f),
        )
        ControlButton(
            symbol = "□",
            label = "DETENER",
            enabled = true,
            tone = PulsoRed,
            onClick = onStop,
            modifier = Modifier.weight(0.82f),
        )
        ControlButton(
            symbol = "×",
            label = "CERRAR MISIÓN",
            enabled = true,
            onClick = onClose,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun ControlButton(
    symbol: String,
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier,
    tone: Color = PulsoInk,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(50.dp),
        shape = RoundedCornerShape(3.dp),
        contentPadding = PaddingValues(horizontal = 4.dp),
        border = BorderStroke(1.dp, if (tone == PulsoRed) PulsoRed.copy(alpha = 0.7f) else PulsoBorder),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = PulsoPanel,
            contentColor = tone,
            disabledContainerColor = PulsoPanelRaised,
            disabledContentColor = PulsoFaint,
        ),
    ) {
        Text(symbol, fontSize = 16.sp, fontWeight = FontWeight.Light)
        Text(
            text = "  $label",
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.Medium,
            letterSpacing = 0.35.sp,
            maxLines = 1,
        )
    }
}
