package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.sensor.SensorMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PulsoInitialStateTest {
    @Test
    fun `production startup contains no replay telemetry`() {
        val state = initialPulsoState(ContextSelector())

        assertEquals(SensorMode.DISCONNECTED, state.sensorMode)
        assertEquals("DISCONNECTED", state.world.source)
        assertEquals(0, state.world.worldSeq)
        assertFalse(state.hasLiveObservation)
        assertTrue(state.world.candidates.isEmpty())
        assertTrue(state.world.obstacles.isEmpty())
        assertTrue(state.world.targets.isEmpty())
        assertTrue(state.world.hypotheses.isEmpty())
        assertTrue(state.metaViewJpeg == null)
        assertTrue(state.egoRgbJpeg == null)
    }
}
