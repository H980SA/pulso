package com.pulso.app.ui

import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.WorldPacket
import com.pulso.app.domain.WorldState
import com.pulso.app.runtime.GemmaRuntimeState
import com.pulso.app.sensor.SensorMode

data class TraceLine(
    val category: String,
    val text: String,
)

data class PulsoUiState(
    val world: WorldState,
    val packet: WorldPacket,
    val cognitive: CognitiveState,
    val checkpoint: MissionCheckpoint,
    val decisionNeed: DecisionNeed,
    val sensorMode: SensorMode = SensorMode.DISCONNECTED,
    val sensorStatus: String = "SIN FUENTE",
    val hasLiveObservation: Boolean = false,
    val lastSensorFrameElapsedMs: Long? = null,
    val metaViewJpeg: ByteArray? = null,
    val egoRgbJpeg: ByteArray? = null,
    val perceptionStatus: String = "COLD",
    val personCount: Int = 0,
    val perceptionLatencyMs: Long? = null,
    val acousticStatus: String = "MIC OFF",
    val roverStatus: String = "DISCONNECTED",
    val roverArmed: Boolean = false,
    val actionRevision: Long = 0,
    val autonomyEnabled: Boolean = false,
    val missionCompletion: MissionCompletion? = null,
    val model: GemmaRuntimeState = GemmaRuntimeState(),
    val trace: List<TraceLine> = emptyList(),
    val lastAgentResponse: String = "Gemma aún no recibió telemetría.",
    val busy: Boolean = false,
)
