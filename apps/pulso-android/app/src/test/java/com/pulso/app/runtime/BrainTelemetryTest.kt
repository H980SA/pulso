package com.pulso.app.runtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BrainTelemetryTest {
    @Test
    fun cancellationIsPublishedAsAFirstClassOperatorEvent() {
        val record = BrainTraceEvent.Canceled(
            turnId = "TURN-9",
            selectedWorldSeq = 9,
            reason = "operator emergency stop",
        ).toTelemetryRecord()

        assertEquals("CANCELED", record.category)
        assertEquals("operator emergency stop", record.summary)
    }

    @Test
    fun packetTraceCarriesOnlyTheActiveDecisionContext() {
        val record = BrainTraceEvent.PacketSelected(
            turnId = "TURN-6",
            selectedWorldSeq = 6,
            candidateCount = 3,
            decisionNeed = "CHOOSE_ROUTE",
            goalId = "G-001",
            checkpointSummary = "2 known · 1 unresolved",
            question = "Which route expands coverage safely?",
            planSummary = "Compare live candidates.",
            activeSkillId = "vio_recovery",
        ).toTelemetryRecord()

        assertEquals("G-001", record.attributes["goal_id"])
        assertEquals("Which route expands coverage safely?", record.attributes["question"])
        assertEquals("vio_recovery", record.attributes["active_skill_id"])
        assertFalse(record.attributes.containsKey("durable_findings"))
    }

    @Test
    fun toolResultDropsSkillInstructionsAndCapabilities() {
        val record = BrainTraceEvent.ToolCompleted(
            turnId = "TURN-7",
            selectedWorldSeq = 7,
            name = "load_skill",
            response = mapOf(
                "accepted" to true,
                "status" to "SKILL_LOADED",
                "skill_id" to "survivor_inspection",
                "instructions" to "private procedural content",
                "candidate_capability" to "opaque-secret",
            ),
        ).toTelemetryRecord()

        assertEquals("TURN-7", record.turnId)
        assertEquals(7L, record.selectedWorldSeq)
        assertEquals("SKILL_LOADED", record.attributes["status"])
        assertFalse(record.attributes.containsKey("instructions"))
        assertFalse(record.attributes.containsKey("candidate_capability"))
        assertFalse(record.summary.contains("private"))
    }

    @Test
    fun toolRequestKeepsOnlyOperatorEvidence() {
        val record = BrainTraceEvent.ToolRequested(
            turnId = "TURN-8",
            selectedWorldSeq = 8,
            name = "move_to",
            arguments = mapOf(
                "target_type" to "FRONTIER",
                "target_id" to "F_A",
                "candidate_capability" to "must-not-leak",
            ),
        ).toTelemetryRecord()

        assertEquals(setOf("target_type", "target_id"), record.attributes.keys)
        assertTrue(record.summary.contains("F_A"))
        assertFalse(record.summary.contains("must-not-leak"))
    }

    @Test
    fun canonicalizedToolResultKeepsRawAndResolvedIdsForAudit() {
        val record = BrainTraceEvent.ToolCompleted(
            turnId = "TURN-9",
            selectedWorldSeq = 9,
            name = "move_to",
            response = mapOf(
                "accepted" to true,
                "status" to "ACCEPTED",
                "requested_target_type" to "FRONTIER",
                "requested_target_id" to "F_+001_+01",
                "resolved_target_type" to "FRONTIER",
                "resolved_target_id" to "F_+001_+001",
                "target_id_canonicalized" to true,
                "candidate_capability" to "must-not-leak",
            ),
        ).toTelemetryRecord()

        assertEquals("F_+001_+01", record.attributes["requested_target_id"])
        assertEquals("F_+001_+001", record.attributes["resolved_target_id"])
        assertEquals(true, record.attributes["target_id_canonicalized"])
        assertFalse(record.attributes.containsKey("candidate_capability"))
    }
}
