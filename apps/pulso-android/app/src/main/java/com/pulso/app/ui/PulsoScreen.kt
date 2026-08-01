package com.pulso.app.ui

import android.opengl.GLSurfaceView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.unit.dp

@Composable
fun PulsoScreen(viewModel: PulsoViewModel, realPreview: GLSurfaceView) {
    val state by viewModel.state.collectAsState()
    var showArDisclosure by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().background(PulsoBackground)) {
        // ARCore requires a live, non-zero GL surface. It stays behind the
        // opaque operator console; CPU RGB/depth are rendered in our own views.
        AndroidView(factory = { realPreview }, modifier = Modifier.size(2.dp))
        Column(
            Modifier
                .fillMaxSize()
                .background(PulsoBackground)
                .padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            PulsoStatusHeader(state)
            Spacer(Modifier.height(8.dp))
            Row(
                Modifier.weight(1f).fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                WorldMap(
                    world = state.world,
                    selectedCandidates = state.packet.candidates.take(6),
                    metaViewJpeg = state.metaViewJpeg,
                    modifier = Modifier.weight(1.34f).fillMaxHeight(),
                )
                BrainConsole(state, Modifier.weight(0.96f).fillMaxHeight())
                WorldPacketConsole(state, Modifier.weight(1.08f).fillMaxHeight())
            }
            Spacer(Modifier.height(8.dp))
            PulsoControls(
                state = state,
                onInitialize = viewModel::initializeModel,
                onConnectReal = { showArDisclosure = true },
                onConnectHil = viewModel::connectHil,
                onAutonomy = viewModel::toggleAutonomy,
                onRun = viewModel::runDecision,
                onNeed = viewModel::toggleDecisionNeed,
                onStop = viewModel::emergencyStop,
                onClose = viewModel::closeMission,
            )
        }
    }
    if (showArDisclosure) {
        AlertDialog(
            onDismissRequest = { showArDisclosure = false },
            title = { Text("Activar percepción del S25") },
            text = {
                Text(
                    "PULSO usará Google Play Services for AR, la cámara, Depth, VIO, " +
                        "IMU y micrófono. El procesamiento queda en el S25; solo la " +
                        "telemetría y evidencias de esta misión se reflejan por el enlace " +
                        "local al operador. El rover permanece detenido hasta recibir INICIAR desde Mission Control."
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showArDisclosure = false
                    viewModel.connectReal()
                }) { Text("ACEPTAR Y CONECTAR") }
            },
            dismissButton = {
                TextButton(onClick = { showArDisclosure = false }) { Text("CANCELAR") }
            },
        )
    }
}
