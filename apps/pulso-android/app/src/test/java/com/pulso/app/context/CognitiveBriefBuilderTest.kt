package com.pulso.app.context

import com.pulso.app.demo.demoWorld
import com.pulso.app.domain.CognitiveState
import org.junit.Assert.assertTrue
import org.junit.Test

class CognitiveBriefBuilderTest {
    @Test
    fun includesLastPhysicalOutcomeForTheNextDecision() {
        val brief = CognitiveBriefBuilder().build(
            world = demoWorld(),
            cognitive = CognitiveState(
                currentQuestion = "Which safe route should Pulso try next?",
                planSummary = "Explore without repeating blocked motion.",
                activeSkillId = null,
                lastActionSummary =
                    "MOVE_TO · FRONTIER:F_A · BLOCKED: obstacle at 0.06m",
            ),
        )

        assertTrue(
            brief.contains("Last action outcome: MOVE_TO · FRONTIER:F_A · BLOCKED")
        )
    }
}
