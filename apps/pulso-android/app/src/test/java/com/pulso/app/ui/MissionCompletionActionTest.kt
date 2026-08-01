package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.domain.ArtifactRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MissionCompletionActionTest {
    @Test
    fun gemmaCompletionIsAcceptedOnlyForCurrentMissionGoalAndEvidence() {
        val state = stateWithEvidence()

        val outcome = applyMissionCompletionAction(
            state,
            mapOf(
                "mission_id" to state.world.mission.id,
                "goal_id" to state.world.activeGoal.id,
                "completion_summary" to "La cobertura asignada y sus hallazgos quedaron verificados.",
                "evidence_refs" to listOf("EV-001"),
                "remaining_risks" to listOf("Zona oeste inaccesible"),
            ),
        )

        assertTrue(outcome.result.accepted)
        assertEquals("MISSION_COMPLETED", outcome.result.status)
        assertFalse(outcome.state.autonomyEnabled)
        assertNotNull(outcome.state.missionCompletion)
        assertEquals(listOf("EV-001"), outcome.state.missionCompletion?.evidenceRefs)
    }

    @Test
    fun completingAnIntermediateOrStaleGoalFailsClosed() {
        val state = stateWithEvidence()
        val outcome = applyMissionCompletionAction(
            state,
            mapOf(
                "mission_id" to state.world.mission.id,
                "goal_id" to "G-OLD",
                "completion_summary" to "Un subobjetivo terminó.",
                "evidence_refs" to listOf("EV-001"),
                "remaining_risks" to emptyList<String>(),
            ),
        )

        assertFalse(outcome.result.accepted)
        assertEquals("STALE_MISSION_CONTEXT", outcome.result.status)
        assertEquals(null, outcome.state.missionCompletion)
    }

    @Test
    fun hallucinatedEvidenceCannotCompleteMission() {
        val state = stateWithEvidence()
        val outcome = applyMissionCompletionAction(
            state,
            mapOf(
                "mission_id" to state.world.mission.id,
                "goal_id" to state.world.activeGoal.id,
                "completion_summary" to "Misión completa.",
                "evidence_refs" to listOf("EV-INVENTADA"),
                "remaining_risks" to emptyList<String>(),
            ),
        )

        assertFalse(outcome.result.accepted)
        assertEquals("UNKNOWN_EVIDENCE_REF", outcome.result.status)
    }

    private fun stateWithEvidence(): PulsoUiState {
        val initial = initialPulsoState(ContextSelector())
        val world = initial.world.copy(
            monotonicNowMs = 42_000,
            artifacts = listOf(ArtifactRef("EV-001", "META_VIEW", 41_000, "ros:///evidence")),
        )
        return initial.copy(world = world, autonomyEnabled = true)
    }
}
