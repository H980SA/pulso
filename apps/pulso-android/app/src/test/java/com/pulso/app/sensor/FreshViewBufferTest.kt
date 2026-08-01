package com.pulso.app.sensor

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class FreshViewBufferTest {
    @Test
    fun returnsOnlyACaptureNewerThanTheRequestBaseline() = runTest {
        val buffer = FreshViewBuffer()
        buffer.update("EGO_RGB", 10, byteArrayOf(1))
        buffer.update("EGO_RGB", 20, byteArrayOf(2))

        val fresh = buffer.awaitAfter("EGO_RGB", 10, 100)

        assertEquals(20L, fresh.capturedMonotonicNs)
        assertArrayEquals(byteArrayOf(2), fresh.jpeg)
    }
}
