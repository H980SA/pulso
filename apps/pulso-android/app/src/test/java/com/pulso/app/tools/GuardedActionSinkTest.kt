package com.pulso.app.tools

import com.pulso.app.domain.CandidateId
import com.pulso.app.domain.CandidateKind
import com.pulso.app.domain.Candidate
import com.pulso.app.domain.Vec2
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GuardedActionSinkTest {
    private var delegatedIntent: ActionIntent? = null
    private val acceptedDelegate = object : PulsoActionSink {
        override suspend fun dispatch(intent: ActionIntent): ActionResult {
            delegatedIntent = intent
            return ActionResult(true, "ACCEPTED", "delegated")
        }
    }

    @Test
    fun rejectsTargetsMissingFromCurrentWorldPacket() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(candidate("VP-17")))

        val result = sink.dispatch(
            ActionIntent(ActionKind.MOVE_TO, CandidateId(CandidateKind.VIEWPOINT, "VP-OLD"))
        )

        assertFalse(result.accepted)
        assertEquals("STALE_OR_UNKNOWN_TARGET", result.status)
    }

    @Test
    fun delegatesCurrentTypedTarget() = runTest {
        val target = CandidateId(CandidateKind.VIEWPOINT, "VP-17")
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(candidate("VP-17")))

        val result = sink.dispatch(ActionIntent(ActionKind.MOVE_TO, target))

        assertTrue(result.accepted)
        assertEquals("capability_current_123456", delegatedIntent?.candidateCapability)
        assertEquals(27L, delegatedIntent?.expectedNavigationRevision)
        assertEquals(4L, delegatedIntent?.expectedTrackingEpoch)
        assertEquals("VP-17", result.data["requested_target_id"])
        assertEquals("VP-17", result.data["resolved_target_id"])
        assertEquals(false, result.data["target_id_canonicalized"])
    }

    @Test
    fun uniquelyCanonicalizesZeroPaddingAndIncompleteStructuralPrefix() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(candidate("F_+001_+001", CandidateKind.FRONTIER)))

        val padded = sink.dispatch(
            ActionIntent(ActionKind.MOVE_TO, CandidateId(CandidateKind.FRONTIER, "F_+001_+01"))
        )
        assertTrue(padded.accepted)
        assertEquals("F_+001_+001", delegatedIntent?.target?.value)
        assertEquals("F_+001_+01", padded.data["requested_target_id"])
        assertEquals("F_+001_+001", padded.data["resolved_target_id"])
        assertEquals(true, padded.data["target_id_canonicalized"])

        val incomplete = sink.dispatch(
            ActionIntent(ActionKind.REQUEST_VIEW, CandidateId(CandidateKind.FRONTIER, "F_+0001"))
        )
        assertTrue(incomplete.accepted)
        assertEquals("F_+001_+001", delegatedIntent?.target?.value)
        assertEquals("F_+0001", incomplete.data["requested_target_id"])
    }

    @Test
    fun ambiguousPrefixAndCrossTypeCandidatesFailClosed() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(
            candidate("F_+001_+001", CandidateKind.FRONTIER),
            candidate("F_+001_+002", CandidateKind.FRONTIER),
            candidate("F_+001", CandidateKind.VIEWPOINT),
        ))
        delegatedIntent = null

        val ambiguous = sink.dispatch(
            ActionIntent(ActionKind.REQUEST_VIEW, CandidateId(CandidateKind.FRONTIER, "F_+0001"))
        )

        assertFalse(ambiguous.accepted)
        assertEquals("AMBIGUOUS_TARGET_ID", ambiguous.status)
        assertEquals("F_+0001", ambiguous.data["requested_target_id"])
        assertEquals(null, delegatedIntent)
    }

    @Test
    fun targetNeverCanonicalizesIntoMoveAuthorization() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(candidate("PERSON_1", CandidateKind.TARGET)))
        delegatedIntent = null

        val result = sink.dispatch(
            ActionIntent(ActionKind.MOVE_TO, CandidateId(CandidateKind.TARGET, "PERSON_0001"))
        )

        assertFalse(result.accepted)
        assertEquals("TARGET_TYPE_MISMATCH", result.status)
        assertEquals("PERSON_0001", result.data["requested_target_id"])
        assertEquals(null, delegatedIntent)
    }

    @Test
    fun arbitraryTyposAreNotFuzzilyAuthorized() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.updateAllowedCandidates(listOf(candidate("F_+001_+001", CandidateKind.FRONTIER)))

        val result = sink.dispatch(
            ActionIntent(ActionKind.MOVE_TO, CandidateId(CandidateKind.FRONTIER, "F_+OO1_+001"))
        )

        assertFalse(result.accepted)
        assertEquals("STALE_OR_UNKNOWN_TARGET", result.status)
    }

    @Test
    fun invalidatedTurnRejectsLateStateChanges() = runTest {
        val sink = GuardedActionSink(acceptedDelegate)
        sink.beginTurn(listOf(candidate("VP-17")))
        sink.invalidateTurn()

        val result = sink.dispatch(
            ActionIntent(ActionKind.LOOK_AT, CandidateId(CandidateKind.VIEWPOINT, "VP-17"))
        )

        assertFalse(result.accepted)
        assertEquals("CANCELED_TURN", result.status)
    }

    private fun candidate(id: String, kind: CandidateKind = CandidateKind.VIEWPOINT) = Candidate(
        id = CandidateId(kind, id),
        position = Vec2(1f, 2f),
        label = "view",
        purpose = "inspect",
        pathLengthM = 1f,
        risk = 0.1f,
        informationGain = 0.8f,
        navigationRevision = 27,
        trackingEpoch = 4,
        validUntilMonotonicMs = 10_000,
        capability = "capability_current_123456",
    )
}
