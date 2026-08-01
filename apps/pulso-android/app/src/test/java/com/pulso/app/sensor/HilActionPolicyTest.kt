package com.pulso.app.sensor

import org.junit.Assert.assertTrue
import org.junit.Test

class HilActionPolicyTest {
    @Test
    fun blockedIsTerminalSoGemmaReceivesTheSafetyOutcomeImmediately() {
        assertTrue(HIL_TERMINAL_STATUSES.contains("BLOCKED"))
        assertTrue(HIL_TERMINAL_STATUSES.contains("TARGET_TOO_CLOSE"))
    }
}
