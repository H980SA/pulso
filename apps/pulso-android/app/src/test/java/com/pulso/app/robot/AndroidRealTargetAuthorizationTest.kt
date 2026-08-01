package com.pulso.app.robot

import com.pulso.app.domain.CandidateId
import com.pulso.app.domain.CandidateKind
import com.pulso.app.sensor.NavigationCandidateObservation
import com.pulso.app.sensor.NavigationObservation
import com.pulso.app.tools.ActionIntent
import com.pulso.app.tools.ActionKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class AndroidRealTargetAuthorizationTest {
    private val grant = "grant_0123456789abcdef0123456789abcdef"
    private val candidate = NavigationCandidateObservation(
        type = "FRONTIER",
        id = "F-1-2",
        label = "Frontera",
        purpose = "Expandir",
        x = 1f,
        y = 2f,
        pathLengthM = 2.2f,
        risk = 0.1f,
        informationGain = 0.8f,
        targetRevision = 4,
        capability = grant,
    )
    private val navigation = NavigationObservation(
        capturedMonotonicNs = 1_000_000_000L,
        sensorMapSeq = 3,
        navigationRevision = 3,
        validUntilMonotonicNs = 16_000_000_000L,
        candidates = listOf(candidate),
    )

    @Test
    fun callAfterOneSecondRemainsValidWhenLatestGeometryAndGrantStillMatch() {
        val intent = intent(grant)

        val authorized = authorizeCurrentCandidate(intent, navigation, 8_100_000_000L)

        assertSame(candidate, authorized)
        assertEquals(true, candidateTypeAllows(candidate, ActionKind.MOVE_TO))
    }

    @Test
    fun requestViewUsesTheSameLongDecisionWindowAndOpaqueGrant() {
        val intent = intent(grant).copy(kind = ActionKind.REQUEST_VIEW)

        val authorized = authorizeCurrentCandidate(intent, navigation, 8_100_000_000L)

        assertSame(candidate, authorized)
        assertEquals(true, candidateTypeAllows(candidate, ActionKind.REQUEST_VIEW))
    }

    @Test
    fun mismatchedOrMissingGrantFailsClosed() {
        assertNull(authorizeCurrentCandidate(intent("grant_wrong_0123456789"), navigation, 8_100_000_000L))
        assertNull(authorizeCurrentCandidate(intent(null), navigation, 8_100_000_000L))
    }

    @Test
    fun expiredSceneFailsClosedAndActionComesFromTypeNotGrant() {
        assertNull(authorizeCurrentCandidate(intent(grant), navigation, 16_000_000_001L))
        assertEquals(false, candidateTypeAllows(candidate, ActionKind.LOOK_AT))
        assertEquals(true, candidateTypeAllows(candidate, ActionKind.REQUEST_VIEW))
    }

    @Test
    fun candidateThatDisappearedFromLatestMeasuredSceneFailsClosed() {
        assertNull(
            authorizeCurrentCandidate(
                intent(grant),
                navigation.copy(candidates = emptyList()),
                8_100_000_000L,
            )
        )
    }

    @Test
    fun measuredTargetAllowsLookAndViewButNeverMove() {
        val target = candidate.copy(type = "TARGET", id = "PERSON_1")

        assertEquals(true, candidateTypeAllows(target, ActionKind.LOOK_AT))
        assertEquals(true, candidateTypeAllows(target, ActionKind.REQUEST_VIEW))
        assertEquals(false, candidateTypeAllows(target, ActionKind.MOVE_TO))
    }

    private fun intent(candidateGrant: String?) = ActionIntent(
        kind = ActionKind.MOVE_TO,
        target = CandidateId(CandidateKind.FRONTIER, "F-1-2"),
        candidateCapability = candidateGrant,
        expectedTargetRevision = 4,
    )
}
