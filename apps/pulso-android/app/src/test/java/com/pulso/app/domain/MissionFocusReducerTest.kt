package com.pulso.app.domain

import com.pulso.app.demo.demoWorld
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MissionFocusReducerTest {
    @Test
    fun focusSurvivesCompactionThroughTheCheckpoint() {
        val world = demoWorld()
        val checkpoint = MissionCheckpoint(
            missionId = world.mission.id,
            goalId = world.activeGoal.id,
            durableFindings = listOf("Map initialized"),
            rejectedAlternatives = emptyList(),
            unresolved = emptyList(),
        )
        val cognitive = CognitiveState("Where next?", "Survey", null, null)
        val result = reduceMissionFocus(
            world,
            checkpoint,
            cognitive,
            title = "Verify candidate A",
            successCondition = "Obtain one fresh target view",
            reason = "A pose clue has the highest information value",
        )

        assertEquals(result.world.activeGoal.id, result.checkpoint.goalId)
        assertEquals(world.semanticRevision + 1, result.world.semanticRevision)
        assertTrue(result.checkpoint.durableFindings.last().contains("Verify candidate A"))
        assertTrue(result.cognitive.currentQuestion.contains(result.world.activeGoal.id))
    }
}
