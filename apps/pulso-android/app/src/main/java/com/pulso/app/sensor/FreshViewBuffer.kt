package com.pulso.app.sensor

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeout

internal data class CapturedView(
    val kind: String,
    val capturedMonotonicNs: Long,
    val jpeg: ByteArray,
)

/** Keeps only fresh camera evidence; it is mission memory, not chat history. */
internal class FreshViewBuffer {
    private val events = MutableSharedFlow<CapturedView>(
        extraBufferCapacity = 4,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    private val latest = mutableMapOf<String, CapturedView>()

    @Synchronized
    fun update(kind: String, capturedNs: Long, jpeg: ByteArray) {
        val view = CapturedView(kind, capturedNs, jpeg)
        latest[kind] = view
        events.tryEmit(view)
    }

    @Synchronized
    fun latest(kind: String): CapturedView? = latest[kind]

    suspend fun awaitAfter(kind: String, capturedNs: Long, timeoutMs: Long): CapturedView {
        latest(kind)?.takeIf { it.capturedMonotonicNs > capturedNs }?.let { return it }
        return withTimeout(timeoutMs) {
            events.first { it.kind == kind && it.capturedMonotonicNs > capturedNs }
        }
    }
}
