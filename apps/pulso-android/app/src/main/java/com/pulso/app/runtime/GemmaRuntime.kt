package com.pulso.app.runtime

import android.content.Context
import com.google.adk.kt.agents.Instruction
import com.google.adk.kt.agents.LlmAgent
import com.google.adk.kt.litertlm.LiteRtLmModel
import com.google.adk.kt.runners.InMemoryRunner
import com.google.adk.kt.sessions.InMemorySessionService
import com.google.adk.kt.sessions.SessionKey
import com.google.adk.kt.tools.FunctionTool
import com.google.adk.kt.types.Blob
import com.google.adk.kt.types.Content
import com.google.adk.kt.types.Part
import com.google.adk.kt.types.Role
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.LogSeverity
import com.pulso.app.domain.WorldPacket
import com.pulso.app.tools.GuardedActionSink
import com.pulso.app.tools.CompleteMissionTool
import com.pulso.app.tools.LoadSkillTool
import com.pulso.app.tools.LookAtTool
import com.pulso.app.tools.ListenTool
import com.pulso.app.tools.MoveToTool
import com.pulso.app.tools.PulsoActionSink
import com.pulso.app.tools.RequestViewTool
import com.pulso.app.tools.SetFlashlightTool
import com.pulso.app.tools.SetMissionFocusTool
import com.pulso.app.tools.SpeakTool
import com.pulso.app.tools.SkillLibrary
import com.pulso.app.tools.StopMotionTool
import com.pulso.app.tools.UpdateHypothesisTool
import java.io.File
import kotlin.system.measureTimeMillis
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

enum class ModelStatus { NOT_INSTALLED, COLD, LOADING, READY, THINKING, ERROR }

data class GemmaRuntimeState(
    val status: ModelStatus = ModelStatus.COLD,
    val backend: String? = null,
    val loadLatencyMs: Long? = null,
    val lastLoopLatencyMs: Long? = null,
    val detail: String = "Model runtime is cold.",
)

sealed interface BrainTraceEvent {
    val turnId: String?
    val selectedWorldSeq: Long?

    data class PacketSelected(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val candidateCount: Int,
        val decisionNeed: String,
        val goalId: String,
        val checkpointSummary: String,
        val question: String,
        val planSummary: String,
        val activeSkillId: String?,
    ) : BrainTraceEvent

    data class ToolRequested(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val name: String,
        val arguments: Map<String, Any?>,
    ) : BrainTraceEvent

    data class ToolCompleted(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val name: String,
        val response: Map<String, Any?>,
    ) : BrainTraceEvent

    data class Response(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val text: String,
    ) : BrainTraceEvent

    data class CycleCompleted(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val latencyMs: Long,
    ) : BrainTraceEvent

    data class Canceled(
        override val turnId: String,
        override val selectedWorldSeq: Long,
        val reason: String,
    ) : BrainTraceEvent

    data class Failure(
        override val turnId: String? = null,
        override val selectedWorldSeq: Long? = null,
        val detail: String,
    ) : BrainTraceEvent
}

class GemmaRuntime(context: Context) {
    private val applicationContext = context.applicationContext
    private val lifecycleMutex = Mutex()
    private val _state = MutableStateFlow(GemmaRuntimeState())
    private val _events = MutableSharedFlow<BrainTraceEvent>(extraBufferCapacity = 64)
    private val skillLibrary = SkillLibrary(applicationContext)
    private val systemPrompt = pulsoSystemPrompt(skillLibrary.catalog())

    private var engine: Engine? = null
    private var model: LiteRtLmModel? = null
    private var runner: InMemoryRunner? = null
    private var guardedSink: GuardedActionSink? = null
    private var toolContracts: ToolContractSnapshot? = null

    val state: StateFlow<GemmaRuntimeState> = _state.asStateFlow()
    val events: SharedFlow<BrainTraceEvent> = _events.asSharedFlow()

    @OptIn(ExperimentalApi::class)
    suspend fun initialize(modelFile: File, actionSink: PulsoActionSink): Result<Unit> =
        lifecycleMutex.withLock {
            if (runner != null) return@withLock Result.success(Unit)
            if (!modelFile.isFile) {
                _state.value = GemmaRuntimeState(
                    status = ModelStatus.NOT_INSTALLED,
                    detail = "Model not found at ${modelFile.absolutePath}",
                )
                return@withLock Result.failure(IllegalStateException("Model file not installed"))
            }

            _state.value = GemmaRuntimeState(ModelStatus.LOADING, detail = "Loading Gemma 4 E4B…")
            Engine.setNativeMinLogSeverity(LogSeverity.ERROR)
            ExperimentalFlags.enableSpeculativeDecoding = true
            val cachePath = File(applicationContext.cacheDir, "litertlm").apply { mkdirs() }.path

            val attempts = listOf(
                "GPU" to EngineConfig(
                    modelPath = modelFile.absolutePath,
                    backend = Backend.GPU(),
                    visionBackend = Backend.GPU(),
                    cacheDir = cachePath,
                ),
                "CPU" to EngineConfig(
                    modelPath = modelFile.absolutePath,
                    backend = Backend.CPU(),
                    visionBackend = Backend.CPU(),
                    cacheDir = cachePath,
                ),
            )

            var lastFailure: Throwable? = null
            for ((backendName, config) in attempts) {
                val candidateEngine = Engine(config)
                try {
                    var loadMs = 0L
                    withContext(Dispatchers.IO) {
                        loadMs = measureTimeMillis { candidateEngine.initialize() }
                    }
                    val candidateModel = LiteRtLmModel.create(candidateEngine, name = "gemma-4-e4b")
                    val candidateSink = GuardedActionSink(actionSink)
                    val tools = createTools(candidateSink)
                    val candidateToolContracts = captureToolContracts(
                        tools.map { tool ->
                            requireNotNull(tool.declaration()) {
                                "Function tool ${tool.name} has no declaration"
                            }
                        }
                    )
                    val agent = createAgent(candidateModel, tools)
                    val sessionService = InMemorySessionService()
                    sessionService.createSession(SessionKey(APP_NAME, USER_ID, SESSION_ID))

                    engine = candidateEngine
                    model = candidateModel
                    guardedSink = candidateSink
                    toolContracts = candidateToolContracts
                    runner = InMemoryRunner(
                        agent = agent,
                        appName = APP_NAME,
                        sessionService = sessionService,
                    )
                    _state.value = GemmaRuntimeState(
                        status = ModelStatus.READY,
                        backend = backendName,
                        loadLatencyMs = loadMs,
                        detail = "Gemma is warm and ready on $backendName.",
                    )
                    return@withLock Result.success(Unit)
                } catch (failure: Throwable) {
                    lastFailure = failure
                    runCatching { candidateEngine.close() }
                }
            }

            val failure = lastFailure ?: IllegalStateException("No LiteRT-LM backend was attempted")
            _state.value = GemmaRuntimeState(
                status = ModelStatus.ERROR,
                detail = failure.message ?: failure::class.simpleName.orEmpty(),
            )
            _events.tryEmit(BrainTraceEvent.Failure(detail = _state.value.detail))
            Result.failure(failure)
        }

    suspend fun think(
        packet: WorldPacket,
        beforeInference: (GemmaTurnInput) -> Unit = {},
    ): Result<String> = lifecycleMutex.withLock {
        val activeRunner = runner
            ?: return@withLock Result.failure(IllegalStateException("Gemma is not initialized"))
        val activeToolContracts = toolContracts
            ?: return@withLock Result.failure(IllegalStateException("Gemma tools are not initialized"))
        val turnId = "TURN-${packet.worldSeq}-${System.nanoTime()}"
        val turnInput = runCatching {
            prepareGemmaTurnInput(
                packet = packet,
                turnId = turnId,
                systemPrompt = systemPrompt,
                toolContracts = activeToolContracts,
            )
        }.getOrElse { failure ->
            _events.tryEmit(BrainTraceEvent.Failure(turnId, packet.worldSeq, failure.message.orEmpty()))
            return@withLock Result.failure(failure)
        }
        guardedSink?.beginTurn(packet.candidates)
        _events.tryEmit(
            BrainTraceEvent.PacketSelected(
                turnId = turnId,
                selectedWorldSeq = packet.worldSeq,
                candidateCount = packet.candidates.size,
                decisionNeed = packet.decisionNeed.name,
                goalId = packet.checkpoint.goalId,
                checkpointSummary =
                    "${packet.checkpoint.durableFindings.size} known · " +
                    "${packet.checkpoint.unresolved.size} unresolved",
                question = packet.cognitiveState.currentQuestion,
                planSummary = packet.cognitiveState.planSummary,
                activeSkillId = packet.cognitiveState.activeSkillId,
            )
        )
        _state.value = _state.value.copy(status = ModelStatus.THINKING, detail = "Choosing next action…")

        var finalText = ""
        var toolInputSequence = 0
        val elapsed = try {
            measureTimeMillis {
                runAfterGemmaInputPublished(turnInput, beforeInference) {
                    val parts = buildList {
                        add(Part(text = requireNotNull(turnInput.promptText)))
                        turnInput.image?.let { image ->
                            add(Part(inlineData = Blob(mimeType = GEMMA_VISUAL_MIME_TYPE, data = image.jpegBytes)))
                        }
                    }
                    activeRunner.runAsync(
                        userId = USER_ID,
                        sessionId = SESSION_ID,
                        newMessage = Content(role = Role.USER, parts = parts),
                    ).collect { event ->
                        event.functionCalls().forEach { call ->
                            _events.tryEmit(
                                BrainTraceEvent.ToolRequested(
                                    turnId,
                                    packet.worldSeq,
                                    call.name,
                                    call.args,
                                )
                            )
                        }
                        val functionResponses = event.functionResponses()
                        functionResponses.forEach { response ->
                            _events.tryEmit(
                                BrainTraceEvent.ToolCompleted(
                                    turnId,
                                    packet.worldSeq,
                                    response.name,
                                    response.response,
                                )
                            )
                        }
                        if (functionResponses.isNotEmpty()) {
                            toolInputSequence += 1
                            val toolResultInput = prepareGemmaToolResultInput(
                                initialInput = turnInput,
                                sequence = toolInputSequence,
                                responses = functionResponses.map { response ->
                                    GemmaToolResponseInput(response.name, response.response)
                                },
                            )
                            // This event is yielded before ADK advances the same
                            // turn, so enqueue its exact harness input now.
                            runCatching { beforeInference(toolResultInput) }
                        }
                        if (event.author == AGENT_NAME && event.isFinalResponse) {
                            finalText = event.content?.parts
                                ?.filter { it.thought != true }
                                ?.mapNotNull { it.text }
                                ?.joinToString("")
                                .orEmpty()
                        }
                    }
                }
            }
        } catch (cancellation: CancellationException) {
            guardedSink?.invalidateTurn()
            _state.value = _state.value.copy(
                status = ModelStatus.READY,
                detail = "Decision turn canceled safely.",
            )
            _events.tryEmit(
                BrainTraceEvent.Canceled(
                    turnId,
                    packet.worldSeq,
                    cancellation.message ?: "Operator or safety preemption",
                )
            )
            throw cancellation
        } catch (failure: Throwable) {
            guardedSink?.invalidateTurn()
            _state.value = _state.value.copy(
                status = ModelStatus.ERROR,
                detail = failure.message ?: failure::class.simpleName.orEmpty(),
            )
            _events.tryEmit(
                BrainTraceEvent.Failure(turnId, packet.worldSeq, _state.value.detail)
            )
            return@withLock Result.failure(failure)
        }

        guardedSink?.invalidateTurn()
        if (finalText.isNotBlank()) {
            _events.tryEmit(BrainTraceEvent.Response(turnId, packet.worldSeq, finalText))
        }
        _events.tryEmit(BrainTraceEvent.CycleCompleted(turnId, packet.worldSeq, elapsed))
        _state.value = _state.value.copy(
            status = ModelStatus.READY,
            lastLoopLatencyMs = elapsed,
            detail = "Decision loop complete.",
        )
        Result.success(finalText)
    }

    /** Preempts the active turn without unloading the warm E4B model. */
    fun cancelCurrentTurn(reason: String) {
        guardedSink?.invalidateTurn()
        if (_state.value.status == ModelStatus.THINKING) {
            _state.value = _state.value.copy(
                status = ModelStatus.READY,
                detail = "Decision preempted: $reason",
            )
        }
    }

    suspend fun closeMission() = lifecycleMutex.withLock {
        runCatching { model?.close() }
        runCatching { engine?.close() }
        runner = null
        model = null
        engine = null
        guardedSink = null
        toolContracts = null
        _state.value = GemmaRuntimeState(ModelStatus.COLD, detail = "Mission runtime closed.")
    }

    private fun createTools(actionSink: GuardedActionSink): List<FunctionTool> = listOf(
        MoveToTool(actionSink),
        LookAtTool(actionSink),
        RequestViewTool(actionSink),
        StopMotionTool(actionSink),
        SetFlashlightTool(actionSink),
        SpeakTool(actionSink),
        ListenTool(actionSink),
        SetMissionFocusTool(actionSink),
        UpdateHypothesisTool(actionSink),
        LoadSkillTool(skillLibrary, actionSink),
        CompleteMissionTool(actionSink),
    )

    private fun createAgent(model: LiteRtLmModel, tools: List<FunctionTool>) = LlmAgent(
        name = AGENT_NAME,
        model = model,
        instruction = Instruction(systemPrompt),
        tools = tools,
        includeContents = LlmAgent.IncludeContents.NONE,
        maxSteps = 4,
    )

    private companion object {
        const val APP_NAME = "pulso"
        const val USER_ID = "local-operator"
        const val SESSION_ID = "active-mission"
        const val AGENT_NAME = "pulso_brain"
    }
}
