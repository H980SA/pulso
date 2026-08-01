package com.pulso.app.ui

import com.pulso.app.context.ContextSelector
import com.pulso.app.demo.demoWorld
import org.junit.Assert.assertNotEquals
import org.junit.Test

class AutonomyFingerprintTest {
    @Test
    fun relocalizationAndLeaseRotationWakeTheAutonomyLoop() {
        val initial = initialPulsoState(ContextSelector())
        val withCandidate = initial.copy(
            world = demoWorld().copy(candidates = demoWorld().candidates.map {
                it.copy(targetRevision = 1, capability = "grant_0123456789abcdef")
            }),
        )
        val relocalized = withCandidate.copy(
            world = withCandidate.world.copy(
                robot = withCandidate.world.robot.copy(trackingEpoch = withCandidate.world.robot.trackingEpoch + 1),
            ),
        )
        val rotated = withCandidate.copy(
            world = withCandidate.world.copy(
                candidates = withCandidate.world.candidates.map { it.copy(targetRevision = 2) },
            ),
        )

        assertNotEquals(autonomyFingerprint(withCandidate), autonomyFingerprint(relocalized))
        assertNotEquals(autonomyFingerprint(withCandidate), autonomyFingerprint(rotated))
    }
}
