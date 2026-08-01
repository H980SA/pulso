package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.Goal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LiveMissionAdmissionTest {
    @Test
    fun firstLiveFrameAlignsCognitionAndCheckpointToProjectedGoal() {
        val initial = initialPulsoState(ContextSelector())
        val liveWorld = initial.world.copy(
            source = "GAZEBO_HIL",
            activeGoal = Goal("G-LIVE", "M-001", "Expandir cobertura", "Elegir una ruta segura."),
        )

        val admitted = admitFirstLiveMission(initial, liveWorld)

        assertEquals("G-LIVE", admitted.checkpoint.goalId)
        assertTrue(admitted.cognitive.currentQuestion.contains("Expandir cobertura"))
        assertFalse(admitted.cognitive.currentQuestion.contains("Esperando telemetría"))
        assertEquals(com.pulso.app.domain.DecisionNeed.CHOOSE_ROUTE, admitted.decisionNeed)
    }

    @Test
    fun laterFramesPreserveAgentUpdatedCognitionAndCheckpoint() {
        val initial = initialPulsoState(ContextSelector())
        val custom = initial.copy(
            hasLiveObservation = true,
            cognitive = initial.cognitive.copy(currentQuestion = "Pregunta agentica vigente"),
            checkpoint = initial.checkpoint.copy(goalId = "G-AGENT", unresolved = listOf("Hallazgo abierto")),
        )

        val admitted = admitFirstLiveMission(custom, custom.world)

        assertEquals(custom.cognitive, admitted.cognitive)
        assertEquals(custom.checkpoint, admitted.checkpoint)
        assertEquals(custom.decisionNeed, admitted.decisionNeed)
    }
}
