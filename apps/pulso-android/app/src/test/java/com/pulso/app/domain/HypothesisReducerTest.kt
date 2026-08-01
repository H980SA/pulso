package com.pulso.app.domain

import com.pulso.app.demo.demoWorld
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HypothesisReducerTest {
    @Test
    fun createsGoalLinkedHypothesisAndCompactsEvidenceIntoCheckpoint() {
        val world = demoWorld()
        val checkpoint = MissionCheckpoint(
            missionId = world.mission.id,
            goalId = world.activeGoal.id,
            durableFindings = emptyList(),
            rejectedAlternatives = emptyList(),
            unresolved = emptyList(),
        )
        val cognitive = CognitiveState("question", "plan", null, null)

        val projection = reduceHypothesis(
            world = world,
            checkpoint = checkpoint,
            cognitive = cognitive,
            requestedId = "NEW",
            claim = "C03 puede ser una persona parcialmente ocluida",
            confidence = 0.72f,
            unresolved = listOf("¿Responde a una pregunta de voz?"),
            evidenceRefs = listOf("EV-21"),
        )

        assertEquals(world.activeGoal.id, projection.hypothesis.goalId)
        assertEquals(listOf("EV-21"), projection.evidenceRefs)
        assertEquals(projection.hypothesis.id, projection.world.hypotheses.last().id)
        assertEquals(projection.hypothesis.id, projection.checkpoint.durableFindings.single().substringBefore(':'))
        assertTrue(projection.cognitive.currentQuestion.contains("voz"))
    }
}
