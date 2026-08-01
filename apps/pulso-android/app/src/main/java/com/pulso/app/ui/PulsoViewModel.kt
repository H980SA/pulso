package com.pulso.app.ui

import android.app.Application
import android.os.SystemClock
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.pulso.app.BuildConfig
import com.pulso.app.PulsoApplication
import com.pulso.app.context.ContextSelector
import com.pulso.app.audio.AcousticAlert
import com.pulso.app.domain.AcousticObservation
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MotionState
import com.pulso.app.domain.VisualView
import com.pulso.app.domain.WorldPacket
import com.pulso.app.domain.WorldState
import com.pulso.app.domain.projectDetections
import com.pulso.app.domain.projectHilWorld
import com.pulso.app.domain.projectSensorWorld
import com.pulso.app.perception.PersonDetection
import com.pulso.app.perception.PersonDetector
import com.pulso.app.perception.PersonPerceptionRunner
import com.pulso.app.runtime.BrainTraceEvent
import com.pulso.app.runtime.ModelStatus
import com.pulso.app.runtime.MissionEventJournal
import com.pulso.app.runtime.toTelemetryRecord
import com.pulso.app.robot.AndroidRealBundle
import com.pulso.app.sensor.GazeboHilSource
import com.pulso.app.sensor.OperatorBridge
import com.pulso.app.sensor.OperatorCommand
import com.pulso.app.sensor.SensorFrame
import com.pulso.app.sensor.SensorMode
import com.pulso.app.tools.ActionIntent
import com.pulso.app.tools.ActionKind
import com.pulso.app.tools.ActionResult
import com.pulso.app.tools.PulsoActionSink
import java.io.File
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class PulsoViewModel(application: Application) : AndroidViewModel(application) {
    private val selector = ContextSelector()
    private val gemma = (application as PulsoApplication).gemmaRuntime
    private val _state = MutableStateFlow(initialPulsoState(selector))
    private var hilSource: GazeboHilSource? = null
    private var hilObservationJob: Job? = null
    private var hilActionJob: Job? = null
    private var decisionJob: Job? = null
    private var decisionEpoch = 0L
    private var hilMissionStartNs: Long? = null
    private var realBundle: AndroidRealBundle? = null
    private var realObservationJob: Job? = null
    private var realSceneJob: Job? = null
    private var realStatusJob: Job? = null
    private var realAudioJob: Job? = null
    private var realMissionStartNs: Long? = null
    private var operatorBridge: OperatorBridge? = null
    private var operatorCommandJob: Job? = null
    private var requestedVisual: VisualView? = null
    private val perceptionRunner = PersonPerceptionRunner(application)
    private val journal = MissionEventJournal(application)
    private var detectionRevision = 0L
    private var lastDetectionSignature = ""
    private var lastAutonomyFingerprint = ""
    private var lastAutonomyRunMs = 0L
    private var operatorStopLatched = false
    private var lastRecordedModelStatus: ModelStatus? = null

    val state: StateFlow<PulsoUiState> = _state.asStateFlow()

    private val actionSink = object : PulsoActionSink {
        override suspend fun dispatch(intent: ActionIntent): ActionResult {
            if (operatorStopLatched && intent.kind in MOTION_ACTIONS) {
                return ActionResult(false, "OPERATOR_STOP", "Motion is latched off until autonomy resumes.")
            }
            val result = when (intent.kind) {
                ActionKind.SET_MISSION_FOCUS -> applyMissionFocus(intent.parameters)
                ActionKind.UPSERT_HYPOTHESIS -> applyHypothesis(intent.parameters)
                ActionKind.LOAD_SKILL -> applySkillLoad(intent.parameters)
                ActionKind.COMPLETE_MISSION -> applyMissionCompletion(intent.parameters)
                else -> dispatchToRobot(intent)
            }
            val resultWithStop = if (intent.kind == ActionKind.COMPLETE_MISSION && result.accepted) {
                operatorStopLatched = true
                // Keep the current tool result deliverable, but invalidate every later call in this turn.
                gemma.cancelCurrentTurn("mission completed")
                val stop = dispatchToRobot(
                    ActionIntent(ActionKind.STOP, parameters = mapOf("reason" to "mission complete"))
                )
                appendTrace("MISSION_COMPLETE", "${result.detail} · STOP ${stop.status}")
                result.copy(data = result.data + mapOf("stop_status" to stop.status))
            } else {
                result
            }
            val target = intent.target?.let { "${it.kind}:${it.value}" } ?: "sin target"
            val actionSummary =
                "${intent.kind} · $target · ${resultWithStop.status}: ${resultWithStop.detail}"
            val current = _state.value
            val cognitive = current.cognitive.copy(lastActionSummary = actionSummary)
            _state.value = current.copy(
                cognitive = cognitive,
                packet = selector.select(
                    world = current.world,
                    need = current.decisionNeed,
                    cognitive = cognitive,
                    checkpoint = current.checkpoint,
                    requestedVisual = requestedVisual,
                ),
            )
            appendTrace("ACTION", actionSummary)
            if (_state.value.sensorMode == SensorMode.ANDROID_REAL) {
                operatorBridge?.publishAction(intent, resultWithStop)
            }
            if (intent.kind == ActionKind.REQUEST_VIEW && resultWithStop.accepted) {
                attachLatestView(intent, resultWithStop)
            }
            if (intent.kind in ACTION_WAKE_KINDS && isTerminalActionStatus(resultWithStop.status)) {
                val current = _state.value
                _state.value = current.copy(actionRevision = current.actionRevision + 1)
            }
            return resultWithStop
        }
    }

    init {
        viewModelScope.launch {
            gemma.state.collect { model ->
                _state.value = _state.value.copy(model = model)
                if (lastRecordedModelStatus != model.status) {
                    lastRecordedModelStatus = model.status
                    appendTrace(
                        "MODEL",
                        buildString {
                            append("Gemma 4 E4B ${model.status}")
                            model.backend?.let { append(" · $it") }
                            model.loadLatencyMs?.let { append(" · carga ${it}ms") }
                        },
                    )
                }
            }
        }
        viewModelScope.launch {
            gemma.events.collect { event ->
                when (event) {
                    is BrainTraceEvent.PacketSelected -> appendTrace(
                        "CONTEXT",
                        "WorldPacket #${event.selectedWorldSeq}: ${event.candidateCount} candidatos",
                    )
                    is BrainTraceEvent.ToolRequested -> appendTrace(
                        "TOOL",
                        "${event.name} ${event.arguments}",
                    )
                    is BrainTraceEvent.ToolCompleted -> appendTrace(
                        "RESULT",
                        "${event.name}: ${event.response}",
                    )
                    is BrainTraceEvent.Response -> {
                        _state.value = _state.value.copy(lastAgentResponse = event.text)
                        appendTrace("DECISION", event.text)
                    }
                    is BrainTraceEvent.CycleCompleted -> appendTrace(
                        "LATENCY",
                        "Turno ${event.turnId}: ${event.latencyMs}ms",
                    )
                    is BrainTraceEvent.Canceled -> appendTrace("CANCELED", event.reason)
                    is BrainTraceEvent.Failure -> appendTrace("ERROR", event.detail)
                }
                val record = event.toTelemetryRecord()
                hilSource?.publishBrainTrace(record)
                operatorBridge?.publishBrainTrace(record)
            }
        }
        viewModelScope.launch {
            while (true) {
                delay(1_000)
                val current = _state.value
                if (
                    current.sensorMode !in setOf(SensorMode.GAZEBO_HIL, SensorMode.ANDROID_REAL) ||
                    !current.hasLiveObservation
                ) continue
                val lastFrameMs = current.lastSensorFrameElapsedMs ?: continue
                if (SystemClock.elapsedRealtime() - lastFrameMs <= SENSOR_STALE_AFTER_MS) continue
                operatorStopLatched = true
                cancelActiveDecision("sensor heartbeat lost")
                _state.value = _state.value.copy(
                    autonomyEnabled = false,
                    hasLiveObservation = false,
                    sensorStatus = "${current.sensorMode.name} STALE",
                )
                appendTrace("ERROR", "Telemetría detenida; decisiones y movimiento bloqueados")
                viewModelScope.launch { dispatchOperatorStop("sensor heartbeat lost") }
            }
        }
        viewModelScope.launch {
            while (true) {
                delay(350)
                val current = _state.value
                if (!current.autonomyEnabled || current.busy || !current.hasLiveObservation) continue
                if (current.missionCompletion != null || current.world.robot.motionState == MotionState.MOVING) continue
                if (current.model.status != ModelStatus.READY) continue
                val fingerprint = autonomyFingerprint(current)
                if (fingerprint == lastAutonomyFingerprint) continue
                val nowMs = SystemClock.elapsedRealtime()
                if (nowMs - lastAutonomyRunMs < 1_200) continue
                lastAutonomyFingerprint = fingerprint
                lastAutonomyRunMs = nowMs
                launchDecisionCycle()
            }
        }
        viewModelScope.launch {
            delay(250)
            if (modelFile().isFile && gemma.state.value.status == ModelStatus.COLD) {
                _state.value = _state.value.copy(busy = true)
                appendTrace("MODEL", "Gemma 4 E4B encontrado; calentando runtime local")
                val result = gemma.initialize(modelFile(), actionSink)
                result.exceptionOrNull()?.let {
                    appendTrace("ERROR", "Gemma E4B: ${it.message ?: it::class.simpleName}")
                }
                _state.value = _state.value.copy(busy = false)
            }
        }
    }

    fun connectHil() {
        if (_state.value.busy || hilSource != null) return
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, sensorStatus = "CONNECTING")
            stopRealSession()
            val source = GazeboHilSource(BuildConfig.SIM_HIL_URL)
            val failure = runCatching { source.start() }.exceptionOrNull()
            if (failure != null) {
                source.close()
                _state.value = _state.value.copy(
                    busy = false,
                    sensorStatus = "HIL ERROR",
                )
                appendTrace("ERROR", failure.message ?: "No se pudo conectar a Gazebo HIL")
                return@launch
            }
            hilSource = source
            hilMissionStartNs = null
            _state.value = _state.value.copy(
                busy = false,
                sensorMode = SensorMode.GAZEBO_HIL,
                sensorStatus = "HIL WAITING",
                hasLiveObservation = false,
                lastSensorFrameElapsedMs = null,
            )
            appendTrace("SENSOR", "Conectado a ${BuildConfig.SIM_HIL_URL}")
            hilObservationJob = viewModelScope.launch {
                source.observations.collect(::integrateHilFrame)
            }
            hilActionJob = viewModelScope.launch {
                source.actionEvents.collect { result ->
                    appendTrace("RESULT", "${result.status} · ${result.detail}")
                }
            }
        }
    }

    fun attachRealBundle(bundle: AndroidRealBundle) {
        if (realBundle === bundle) return
        realBundle = bundle
    }

    fun detachRealBundle(bundle: AndroidRealBundle) {
        if (realBundle !== bundle) return
        realObservationJob?.cancel()
        realSceneJob?.cancel()
        realStatusJob?.cancel()
        realAudioJob?.cancel()
        operatorBridge?.close()
        operatorCommandJob?.cancel()
        operatorBridge = null
        realBundle = null
    }

    fun connectReal() {
        if (_state.value.busy || _state.value.sensorMode == SensorMode.ANDROID_REAL) return
        val bundle = realBundle
        if (bundle == null) {
            appendTrace("ERROR", "La Activity todavía no adjuntó el runtime ARCore")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, sensorStatus = "S25 CONNECTING")
            hilObservationJob?.cancel()
            hilActionJob?.cancel()
            hilSource?.close()
            hilSource = null
            val failure = runCatching { bundle.startSensors() }.exceptionOrNull()
            if (failure != null) {
                _state.value = _state.value.copy(busy = false, sensorStatus = "S25 ERROR")
                appendTrace("ERROR", "S25/ARCore: ${failure.message ?: failure::class.simpleName}")
                return@launch
            }
            realMissionStartNs = null
            operatorBridge?.close()
            operatorCommandJob?.cancel()
            operatorBridge = OperatorBridge(BuildConfig.DEFAULT_HIL_URL).also { bridge ->
                runCatching { bridge.start() }.onFailure {
                    appendTrace("TELEMETRY", "Mission Control offline; el cerebro local continúa")
                }
            }
            operatorCommandJob = viewModelScope.launch {
                operatorBridge?.commands?.collect(::handleOperatorCommand)
            }
            val roverConnection = bundle.actions.connectRover()
            _state.value = _state.value.copy(
                busy = false,
                sensorMode = SensorMode.ANDROID_REAL,
                sensorStatus = "S25 WAITING",
                hasLiveObservation = false,
                lastSensorFrameElapsedMs = null,
                acousticStatus = "MIC LIVE",
                roverStatus = roverConnection.status,
                roverArmed = false,
            )
            appendTrace("SENSOR", "Percepción física S25 y micrófono continuo iniciados")
            appendTrace("ROVER", "${roverConnection.status} · ${roverConnection.detail}")
            realObservationJob = viewModelScope.launch {
                bundle.source.observations.collect(::integrateRealFrame)
            }
            realSceneJob = viewModelScope.launch {
                bundle.source.metaViewScenes.collect { operatorBridge?.publishMetaviewScene(it) }
            }
            realStatusJob = viewModelScope.launch {
                bundle.source.status.collect { status ->
                    val current = _state.value
                    if (current.sensorMode == SensorMode.ANDROID_REAL) {
                        val thermalStop = status.startsWith("THERMAL_STOP")
                        _state.value = current.copy(
                            sensorStatus = "S25 $status",
                            autonomyEnabled = if (thermalStop) false else current.autonomyEnabled,
                            hasLiveObservation = if (thermalStop) false else current.hasLiveObservation,
                        )
                        if (thermalStop && !current.sensorStatus.contains("THERMAL_STOP")) {
                            operatorStopLatched = true
                            cancelActiveDecision("phone thermal guard")
                            appendTrace("SAFETY", "$status · inferencia y movimiento pausados")
                            launch { dispatchOperatorStop("phone thermal guard") }
                        }
                    }
                }
            }
            realAudioJob = viewModelScope.launch {
                bundle.audio.alerts.collect(::integrateAcousticAlert)
            }
        }
    }

    fun initializeModel() {
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            gemma.initialize(modelFile(), actionSink)
            _state.value = _state.value.copy(busy = false)
        }
    }

    fun runDecision() {
        if (_state.value.busy || decisionJob?.isActive == true) return
        if (_state.value.missionCompletion != null) {
            appendTrace("BLOCKED", "La misión ya fue completada por Gemma")
            return
        }
        if (!_state.value.hasLiveObservation) {
            appendTrace("BLOCKED", "No hay telemetría viva; Gemma no recibió contexto")
            return
        }
        launchDecisionCycle()
    }

    fun toggleAutonomy() {
        val current = _state.value
        val enabled = !current.autonomyEnabled
        if (enabled && !current.hasLiveObservation) {
            appendTrace("BLOCKED", "Conecta una fuente y espera el primer frame real")
            return
        }
        if (enabled && current.missionCompletion != null) {
            appendTrace("BLOCKED", "Inicia una nueva misión antes de reactivar autonomía")
            return
        }
        if (enabled) {
            operatorStopLatched = false
            lastAutonomyFingerprint = ""
        } else {
            operatorStopLatched = true
            cancelActiveDecision("operator paused autonomy")
            viewModelScope.launch { dispatchOperatorStop("operator paused autonomy") }
        }
        _state.value = _state.value.copy(autonomyEnabled = enabled)
        appendTrace("AUTO", if (enabled) "Loop agentico activado" else "Loop agentico pausado")
    }

    fun toggleDecisionNeed() {
        val current = _state.value
        if (!current.hasLiveObservation) return
        requestedVisual = null
        val next = when (current.decisionNeed) {
            DecisionNeed.CHOOSE_ROUTE -> DecisionNeed.INSPECT_TARGET
            DecisionNeed.INSPECT_TARGET -> DecisionNeed.RECOVER_TRACKING
            DecisionNeed.RECOVER_TRACKING -> DecisionNeed.MONITOR
            DecisionNeed.MONITOR -> DecisionNeed.CHOOSE_ROUTE
        }
        _state.value = current.copy(
            decisionNeed = next,
            packet = selectPacket(current.world, next),
        )
    }

    fun closeMission() {
        operatorStopLatched = true
        cancelActiveDecision("mission closed by operator")
        _state.value = _state.value.copy(autonomyEnabled = false)
        viewModelScope.launch {
            dispatchOperatorStop("mission closed")
            if (_state.value.sensorMode == SensorMode.ANDROID_REAL) stopRealSession()
            gemma.closeMission()
            _state.value = _state.value.copy(
                sensorMode = SensorMode.DISCONNECTED,
                sensorStatus = "MISIÓN CERRADA",
                hasLiveObservation = false,
            )
        }
    }

    fun emergencyStop() {
        operatorStopLatched = true
        cancelActiveDecision("operator emergency stop")
        _state.value = _state.value.copy(autonomyEnabled = false, busy = false)
        viewModelScope.launch {
            dispatchOperatorStop("operator emergency stop")
            realBundle?.actions?.disarmRover("operator emergency stop")
            _state.value = _state.value.copy(roverArmed = false, roverStatus = "ESTOP / DISARMED")
        }
    }

    override fun onCleared() {
        cancelActiveDecision("view model cleared")
        hilObservationJob?.cancel()
        hilActionJob?.cancel()
        perceptionRunner.close()
        hilSource?.close()
        realObservationJob?.cancel()
        realSceneJob?.cancel()
        realStatusJob?.cancel()
        realAudioJob?.cancel()
        operatorBridge?.close()
        operatorCommandJob?.cancel()
        realBundle?.close()
        super.onCleared()
    }

    private suspend fun disconnectedDispatch(intent: ActionIntent): ActionResult {
        return ActionResult(
            false,
            "NO_SENSOR_SOURCE",
            "${intent.kind} rechazado: no hay adaptador de robot conectado.",
        )
    }

    private suspend fun dispatchToRobot(intent: ActionIntent): ActionResult =
        when (_state.value.sensorMode) {
            SensorMode.ANDROID_REAL -> realBundle?.actions?.dispatch(intent)
                ?: disconnectedDispatch(intent)
            else -> hilSource?.dispatch(intent) ?: disconnectedDispatch(intent)
        }

    private suspend fun dispatchOperatorStop(reason: String) {
        val result = dispatchToRobot(ActionIntent(ActionKind.STOP, parameters = mapOf("reason" to reason)))
        appendTrace("STOP", "$reason · ${result.status}")
    }

    private suspend fun integrateAcousticAlert(alert: AcousticAlert) {
        val current = _state.value
        if (current.sensorMode != SensorMode.ANDROID_REAL) return
        val observedMs = alert.capturedMonotonicNs / 1_000_000L
        val observation = AcousticObservation(
            id = alert.id,
            label = "grito intencional posible",
            confidence = alert.confidence,
            durationMs = alert.durationMs,
            rmsDbfs = alert.rmsDbfs,
            marginAboveNoiseDb = alert.marginAboveNoiseDb,
            bearingKnown = alert.bearingKnown,
            observedAtMonotonicMs = observedMs,
            validUntilMonotonicMs = observedMs + ACOUSTIC_ALERT_TTL_MS,
        )
        val world = current.world.copy(
            worldSeq = current.world.worldSeq + 1,
            semanticRevision = current.world.semanticRevision + 1,
            monotonicNowMs = maxOf(current.world.monotonicNowMs, observedMs),
            acousticObservations = (
                current.world.acousticObservations.filter { observedMs <= it.validUntilMonotonicMs } + observation
            ).takeLast(4),
        )
        val cognitive = current.cognitive.copy(
            currentQuestion = "¿Qué barrido visual seguro puede confirmar o descartar el origen del grito sin inventar una dirección?",
            lastActionSummary = "Alerta acústica ${alert.id}; traslación detenida, bearing no medido.",
        )
        val need = DecisionNeed.CHOOSE_ROUTE
        _state.value = current.copy(
            world = world,
            cognitive = cognitive,
            decisionNeed = need,
            packet = selector.select(world, need, cognitive, current.checkpoint, requestedVisual),
            acousticStatus = "ALERTA ${(alert.confidence * 100).toInt()}%",
            actionRevision = current.actionRevision + 1,
        )
        appendTrace(
            "ACOUSTIC",
            "${alert.id}: ${alert.durationMs}ms, ${"%.1f".format(alert.marginAboveNoiseDb)}dB sobre ruido; dirección desconocida",
        )
        dispatchOperatorStop("fresh intentional-scream candidate")
    }

    private suspend fun handleOperatorCommand(command: OperatorCommand) {
        appendTrace("OPERATOR", "WEB ${command.command} · ${command.nonce.take(8)}")
        when (command.command) {
            "ARM_ROVER" -> armRoverFromConsole()
            "START_AUTONOMY" -> {
                if (!_state.value.roverArmed && !armRoverFromConsole()) return
                if (!_state.value.autonomyEnabled) toggleAutonomy()
            }
            "PAUSE_AUTONOMY" -> if (_state.value.autonomyEnabled) toggleAutonomy()
            "STOP_ALL" -> stopAllFromConsole()
        }
    }

    private suspend fun armRoverFromConsole(): Boolean {
        val bundle = realBundle ?: return false
        if (_state.value.sensorMode != SensorMode.ANDROID_REAL || !_state.value.hasLiveObservation) {
            appendTrace("BLOCKED", "WEB ARM: S25 todavía no tiene observación física viva")
            return false
        }
        val result = bundle.actions.armRover(operatorPresent = true)
        val armed = result.accepted && result.status.startsWith("ARMED")
        _state.value = _state.value.copy(roverArmed = armed, roverStatus = result.status)
        appendTrace("ROVER", "${result.status} · ${result.detail}")
        return armed
    }

    private suspend fun stopAllFromConsole() {
        operatorStopLatched = true
        cancelActiveDecision("web operator stop all")
        _state.value = _state.value.copy(autonomyEnabled = false, busy = false)
        dispatchOperatorStop("web operator stop all")
        realBundle?.actions?.disarmRover("web operator stop all")
        _state.value = _state.value.copy(roverArmed = false, roverStatus = "STOP ALL / DISARMED")
    }

    private fun applyMissionFocus(parameters: Map<String, Any>): ActionResult {
        val outcome = applyMissionFocusAction(_state.value, selector, requestedVisual, parameters)
        _state.value = outcome.state
        return outcome.result
    }

    private fun applyHypothesis(parameters: Map<String, Any>): ActionResult {
        val outcome = applyHypothesisAction(_state.value, selector, requestedVisual, parameters)
        _state.value = outcome.state
        return outcome.result
    }

    private fun applySkillLoad(parameters: Map<String, Any>): ActionResult {
        val skillId = (parameters["skill_id"] as? String)?.trim().orEmpty()
        if (skillId.isBlank()) {
            return ActionResult(false, "INVALID_ARGUMENT", "A skill_id is required.")
        }
        val current = _state.value
        val cognitive = current.cognitive.copy(
            activeSkillId = skillId,
            lastActionSummary = "Skill $skillId loaded for this decision.",
        )
        _state.value = current.copy(
            cognitive = cognitive,
            packet = selector.select(
                current.world,
                current.decisionNeed,
                cognitive,
                current.checkpoint,
                requestedVisual,
            ),
        )
        return ActionResult(
            true,
            "SKILL_LOADED",
            "Procedural skill loaded into the current agent turn.",
            mapOf("skill_id" to skillId),
        )
    }

    private fun applyMissionCompletion(parameters: Map<String, Any>): ActionResult {
        val outcome = applyMissionCompletionAction(_state.value, parameters)
        val updated = outcome.state
        _state.value = updated.copy(
            packet = selector.select(
                updated.world,
                updated.decisionNeed,
                updated.cognitive,
                updated.checkpoint,
                requestedVisual,
            ),
        )
        return outcome.result
    }

    private fun integrateHilFrame(frame: SensorFrame) {
        val previous = _state.value
        val envelope = frame.envelope
        val startNs = hilMissionStartNs ?: envelope.capturedMonotonicNs.also { hilMissionStartNs = it }
        val navigationRevision = frame.navigation?.navigationRevision
            ?: previous.world.navigationRevision
        if (requestedVisual?.navigationRevision != navigationRevision) requestedVisual = null
        val world = projectHilWorld(previous.world, frame, startNs)
        val admission = admitFirstLiveMission(previous, world)
        _state.value = previous.copy(
            world = world,
            packet = selector.select(
                world,
                admission.decisionNeed,
                admission.cognitive,
                admission.checkpoint,
                requestedVisual,
            ),
            cognitive = admission.cognitive,
            checkpoint = admission.checkpoint,
            decisionNeed = admission.decisionNeed,
            sensorMode = SensorMode.GAZEBO_HIL,
            sensorStatus = "HIL LIVE",
            hasLiveObservation = true,
            lastSensorFrameElapsedMs = SystemClock.elapsedRealtime(),
            metaViewJpeg = frame.metaViewJpeg ?: previous.metaViewJpeg,
            egoRgbJpeg = frame.egoRgbJpeg ?: previous.egoRgbJpeg,
        )
        schedulePerception(frame)
    }

    private fun integrateRealFrame(frame: SensorFrame) {
        val previous = _state.value
        val startNs = realMissionStartNs ?: frame.envelope.capturedMonotonicNs.also {
            realMissionStartNs = it
        }
        val navigationRevision = frame.navigation?.navigationRevision
            ?: previous.world.navigationRevision
        if (requestedVisual?.navigationRevision != navigationRevision) requestedVisual = null
        val world = projectSensorWorld(previous.world, frame, startNs)
        val admission = admitFirstLiveMission(previous, world)
        _state.value = previous.copy(
            world = world,
            packet = selector.select(
                world,
                admission.decisionNeed,
                admission.cognitive,
                admission.checkpoint,
                requestedVisual,
            ),
            cognitive = admission.cognitive,
            checkpoint = admission.checkpoint,
            decisionNeed = admission.decisionNeed,
            sensorMode = SensorMode.ANDROID_REAL,
            sensorStatus = "S25 LIVE",
            hasLiveObservation = true,
            lastSensorFrameElapsedMs = SystemClock.elapsedRealtime(),
            metaViewJpeg = frame.metaViewJpeg ?: previous.metaViewJpeg,
            egoRgbJpeg = frame.egoRgbJpeg ?: previous.egoRgbJpeg,
        )
        operatorBridge?.publishFrame(frame)
        schedulePerception(frame)
    }

    private fun attachLatestView(intent: ActionIntent, result: ActionResult) {
        val current = _state.value
        val requestedKind = intent.parameters["view_kind"] as? String ?: "CANDIDATE_VIEW"
        val capturedNs = (result.data["artifact_capture_ns"] as? Number)?.toLong()
        val exactJpeg = capturedNs?.let { captureNs ->
            if (current.sensorMode == SensorMode.ANDROID_REAL) {
                realBundle?.source?.latestViewBytes(requestedKind, captureNs)
            } else {
                hilSource?.latestViewBytes(requestedKind, captureNs)
            }
        }
        val currentJpeg = when (requestedKind) {
            "TARGET_VIEW", "CANDIDATE_VIEW" -> current.egoRgbJpeg
            else -> current.metaViewJpeg
        }
        val jpeg = selectAuthorizedView(capturedNs, exactJpeg, currentJpeg)
        if (jpeg == null) {
            val detail = if (capturedNs != null) {
                "$requestedKind no coincide con la captura autorizada $capturedNs"
            } else {
                "$requestedKind todavía no está disponible"
            }
            appendTrace("ERROR", detail)
            return
        }
        val requestActionId = result.data["action_id"] as? String
        if (requestActionId.isNullOrBlank()) {
            appendTrace("ERROR", "$requestedKind no tiene autorización request_view verificable")
            return
        }
        val candidate = current.world.candidates.firstOrNull { it.id == intent.target }
        requestedVisual = VisualView(
            artifactId = "$requestedKind-${current.world.navigationRevision}-${current.world.worldSeq}",
            kind = requestedKind,
            navigationRevision = current.world.navigationRevision,
            requestActionId = requestActionId,
            capturedAtMonotonicMs = capturedNs?.div(1_000_000L),
            targetId = intent.target,
            targetRevision = candidate?.targetRevision,
            jpegBytes = jpeg,
        )
        _state.value = current.copy(
            packet = selectPacket(current.world, current.decisionNeed),
        )
        appendTrace("CONTEXT", "$requestedKind solicitada; se adjuntará al siguiente ciclo")
    }

    private fun schedulePerception(frame: SensorFrame) {
        val jpeg = frame.egoRgbJpeg ?: return
        perceptionRunner.submit(
            scope = viewModelScope,
            jpeg = jpeg,
            calibration = frame.cameraCalibration,
            onWarming = {
                _state.value = _state.value.copy(perceptionStatus = "WARMING")
                hilSource?.publishPerceptionTelemetry(
                    sourceCaptureNs = frame.envelope.capturedMonotonicNs,
                    modelId = PersonDetector.MODEL_ID,
                    status = "WARMING",
                    detectionCount = 0,
                    inferenceLatencyMs = 0,
                    semanticRevision = _state.value.world.semanticRevision,
                )
                operatorBridge?.publishPerceptionTelemetry(
                    frame.envelope.capturedMonotonicNs,
                    PersonDetector.MODEL_ID,
                    "WARMING",
                    0,
                    0,
                    _state.value.world.semanticRevision,
                )
            },
            onResult = { detections -> integrateDetections(frame, detections) },
            onFailure = { failure ->
                _state.value = _state.value.copy(perceptionStatus = "ERROR")
                hilSource?.publishPerceptionTelemetry(
                    sourceCaptureNs = frame.envelope.capturedMonotonicNs,
                    modelId = PersonDetector.MODEL_ID,
                    status = "ERROR",
                    detectionCount = 0,
                    inferenceLatencyMs = 0,
                    semanticRevision = _state.value.world.semanticRevision,
                )
                operatorBridge?.publishPerceptionTelemetry(
                    frame.envelope.capturedMonotonicNs,
                    PersonDetector.MODEL_ID,
                    "ERROR",
                    0,
                    0,
                    _state.value.world.semanticRevision,
                )
                appendTrace("ERROR", "Percepción: ${failure.message ?: failure::class.simpleName}")
            },
        )
    }

    private fun integrateDetections(frame: SensorFrame, detections: List<PersonDetection>) {
        val previous = _state.value
        val projection = projectDetections(
            previous = previous.world,
            previousNeed = previous.decisionNeed,
            frame = frame,
            detections = detections,
            previousDetectionRevision = detectionRevision,
            previousSignature = lastDetectionSignature,
        )
        detectionRevision = projection.revision
        if (frame.envelope.source == SensorMode.ANDROID_REAL) {
            realBundle?.source?.updatePerceptionCandidates(
                projection.navigationCandidates,
                projection.world.navigationRevision,
                frame.envelope.trackingEpoch,
                frame.envelope.capturedMonotonicNs,
            )
        }
        hilSource?.publishPerceptionTracks(
            frame.envelope.capturedMonotonicNs,
            projection.tracks,
        )
        operatorBridge?.publishPerceptionTracks(frame.envelope.capturedMonotonicNs, projection.tracks)
        hilSource?.publishPerceptionTelemetry(
            sourceCaptureNs = frame.envelope.capturedMonotonicNs,
            modelId = PersonDetector.MODEL_ID,
            status = "LIVE",
            detectionCount = detections.size,
            inferenceLatencyMs = projection.latencyMs,
            semanticRevision = projection.world.semanticRevision,
        )
        operatorBridge?.publishPerceptionTelemetry(
            frame.envelope.capturedMonotonicNs,
            PersonDetector.MODEL_ID,
            "LIVE",
            detections.size,
            projection.latencyMs,
            projection.world.semanticRevision,
        )
        _state.value = previous.copy(
            world = projection.world,
            packet = selectPacket(projection.world, projection.decisionNeed),
            decisionNeed = projection.decisionNeed,
            perceptionStatus = "LIVE",
            personCount = detections.size,
            perceptionLatencyMs = projection.latencyMs,
        )
        if (projection.semanticChanged) {
            lastDetectionSignature = projection.signature
            frame.egoRgbJpeg?.let { jpeg ->
                runCatching {
                    journal.persistArtifact(
                        artifactId = "PERCEPTION-${frame.envelope.capturedMonotonicNs}",
                        kind = "EGO_RGB_DETECTION_EVIDENCE",
                        bytes = jpeg,
                        extension = "jpg",
                        metadata = mapOf(
                            "source_capture_ns" to frame.envelope.capturedMonotonicNs,
                            "model_id" to PersonDetector.MODEL_ID,
                            "inference_latency_ms" to projection.latencyMs,
                            "tracks" to projection.tracks.map { track ->
                                mapOf(
                                    "id" to track.id,
                                    "confidence" to track.confidence,
                                    "bearing_deg" to track.bearingDeg,
                                    "bounds" to listOf(
                                        track.leftNorm,
                                        track.topNorm,
                                        track.rightNorm,
                                        track.bottomNorm,
                                    ),
                                )
                            },
                        ),
                    )
                }
            }
            appendTrace(
                "PERCEPTION",
                if (projection.tracks.isEmpty()) "Sin patrón humano en el último frame"
                else "${projection.tracks.size} patrón(es) humano(s); inferencia ${projection.latencyMs}ms",
            )
        }
    }

    private fun launchDecisionCycle() {
        if (decisionJob?.isActive == true || _state.value.busy) return
        val epoch = ++decisionEpoch
        decisionJob = viewModelScope.launch { executeDecisionCycle(epoch) }
    }

    private fun cancelActiveDecision(reason: String) {
        decisionEpoch += 1
        gemma.cancelCurrentTurn(reason)
        decisionJob?.cancel(CancellationException(reason))
        decisionJob = null
        if (_state.value.busy) _state.value = _state.value.copy(busy = false)
    }

    private suspend fun executeDecisionCycle(epoch: Long) {
        if (
            _state.value.busy ||
            _state.value.model.status != ModelStatus.READY ||
            !_state.value.hasLiveObservation ||
            _state.value.missionCompletion != null ||
            _state.value.world.robot.motionState == MotionState.MOVING
        ) return
        _state.value = _state.value.copy(busy = true)
        val packet = _state.value.packet
        val startingNavigationRevision = _state.value.world.navigationRevision
        val startingSemanticRevision = _state.value.world.semanticRevision
        try {
            val result = gemma.think(packet) { input ->
                journal.recordGemmaInput(input)
                hilSource?.publishGemmaInput(input)
                operatorBridge?.publishGemmaInput(input)
            }
            result.exceptionOrNull()?.let { appendTrace("ERROR", it.message ?: "Decision failed") }
            if (packet.visualView != null && epoch == decisionEpoch) {
                requestedVisual = null
                val current = _state.value
                _state.value = current.copy(
                    packet = selectPacket(current.world, current.decisionNeed),
                )
                if (
                    current.world.navigationRevision == startingNavigationRevision &&
                    current.world.semanticRevision == startingSemanticRevision
                ) {
                    lastAutonomyFingerprint = autonomyFingerprint(_state.value)
                }
            }
        } catch (_: CancellationException) {
            // Operator/safety preemption is expected and already visible as CANCELED telemetry.
        } finally {
            if (epoch == decisionEpoch) {
                _state.value = _state.value.copy(busy = false)
                decisionJob = null
            }
        }
    }

    private fun selectPacket(world: WorldState, need: DecisionNeed): WorldPacket = selector.select(
        world = world,
        need = need,
        cognitive = _state.value.cognitive,
        checkpoint = _state.value.checkpoint,
        requestedVisual = requestedVisual,
    )

    private fun modelFile(): File {
        val application = getApplication<Application>()
        val candidates = listOfNotNull(
            application.getExternalFilesDir(null)?.let {
                File(it, "models/gemma-4-E4B-it.litertlm")
            },
            File(application.filesDir, "models/gemma-4-E4B-it.litertlm"),
        )
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    private fun appendTrace(category: String, text: String) {
        runCatching { journal.append(category, text) }
        val current = _state.value
        _state.value = current.copy(
            trace = (current.trace + TraceLine(category, text)).takeLast(12)
        )
    }

    private suspend fun stopRealSession() {
        realObservationJob?.cancel()
        realSceneJob?.cancel()
        realStatusJob?.cancel()
        realAudioJob?.cancel()
        runCatching { realBundle?.actions?.disarmRover("real session stopped") }
        runCatching { realBundle?.stopSensors() }
        operatorBridge?.close()
        operatorCommandJob?.cancel()
        operatorBridge = null
        realMissionStartNs = null
        _state.value = _state.value.copy(
            acousticStatus = "MIC OFF",
            roverStatus = "DISCONNECTED",
            roverArmed = false,
        )
    }

    private companion object {
        val ACTION_WAKE_KINDS = setOf(
            ActionKind.STOP,
            ActionKind.MOVE_TO,
            ActionKind.LOOK_AT,
            ActionKind.REQUEST_VIEW,
            ActionKind.SET_FLASHLIGHT,
            ActionKind.SPEAK,
            ActionKind.LISTEN,
        )
        val MOTION_ACTIONS = setOf(ActionKind.MOVE_TO, ActionKind.LOOK_AT)
        const val SENSOR_STALE_AFTER_MS = 3_000L
        const val ACOUSTIC_ALERT_TTL_MS = 12_000L
    }
}

internal fun isTerminalActionStatus(status: String): Boolean = status !in setOf(
    "ACTIVE",
    "STARTED",
    "PENDING",
    "MOVING",
)

internal fun autonomyFingerprint(state: PulsoUiState): String {
    val candidateLeaseSignature = state.world.candidates
        .sortedWith(compareBy({ it.id.kind.name }, { it.id.value }))
        .joinToString(",") { "${it.id.kind}:${it.id.value}@${it.targetRevision ?: "-"}" }
    return listOf(
        state.world.navigationRevision,
        state.world.semanticRevision,
        state.actionRevision,
        state.world.robot.trackingState,
        state.world.robot.trackingEpoch,
        candidateLeaseSignature,
        state.world.activeGoal.id,
        state.decisionNeed,
        state.packet.visualView?.artifactId,
    ).joinToString(":")
}

internal fun selectAuthorizedView(
    capturedMonotonicNs: Long?,
    exactCapture: ByteArray?,
    currentFallback: ByteArray?,
): ByteArray? = if (capturedMonotonicNs != null) exactCapture else currentFallback
