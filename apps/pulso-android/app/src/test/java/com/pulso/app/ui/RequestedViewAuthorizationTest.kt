package com.pulso.app.ui

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RequestedViewAuthorizationTest {
    @Test
    fun exactCaptureMissNeverFallsBackToCurrentImage() {
        assertNull(
            selectAuthorizedView(
                capturedMonotonicNs = 123L,
                exactCapture = null,
                currentFallback = byteArrayOf(9, 9, 9),
            )
        )
    }

    @Test
    fun fallbackIsOnlyAllowedWhenResultHasNoCaptureTimestamp() {
        val fallback = byteArrayOf(1, 2, 3)
        assertArrayEquals(fallback, selectAuthorizedView(null, null, fallback))
    }
}
