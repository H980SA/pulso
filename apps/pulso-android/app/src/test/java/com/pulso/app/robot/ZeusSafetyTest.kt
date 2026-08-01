package com.pulso.app.robot

import com.pulso.app.sensor.real.RealPose2d
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ZeusSafetyTest {
    @Test
    fun stopFramePressesStopAndZeroesBothJoysticks() {
        val fields = ZeusWireProtocol.encode(ZeusCommand.Stop).split(';')
        assertEquals(26, fields.size)
        assertEquals("1", fields[5])
        assertEquals("0,0", fields[10])
        assertEquals("0,0", fields[16])
    }

    @Test
    fun wirePowerIsConservativelyClamped() {
        val fields = ZeusWireProtocol.encode(ZeusCommand.Drive(0f, 100, 0f)).split(';')
        assertEquals("0,28", fields[10])
    }

    @Test
    fun plannerStopsTranslationWithoutCurrentFrontRange() {
        val pose = RealPose2d(0f, 0f, 0f, 1_000_000_000L)
        val result = ZeusClosedLoopPlanner().plan(
            ClosedLoopTarget(1f, 0f, lookOnly = false),
            ClosedLoopEvidence(pose, frontRangeM = null),
            nowNs = pose.capturedMonotonicNs,
        )

        assertEquals(ZeusCommand.Stop, result.command)
        assertEquals("NO_CURRENT_FRONT_RANGE", result.terminalStatus)
    }

    @Test
    fun plannerStopsStaleVioAndBlockedFront() {
        val pose = RealPose2d(0f, 0f, 0f, 1_000_000_000L)
        val planner = ZeusClosedLoopPlanner()
        assertEquals(
            "STALE_VIO",
            planner.plan(
                ClosedLoopTarget(1f, 0f, false),
                ClosedLoopEvidence(pose, 2f),
                pose.capturedMonotonicNs + ZeusClosedLoopPlanner.MAX_EVIDENCE_AGE_NS + 1,
            ).terminalStatus,
        )
        assertEquals(
            "FRONT_BLOCKED",
            planner.plan(
                ClosedLoopTarget(1f, 0f, false),
                ClosedLoopEvidence(pose, 0.2f),
                pose.capturedMonotonicNs,
            ).terminalStatus,
        )
    }

    @Test
    fun clientDefaultsDryRunAndRejectsMotionBeforeConnectionAndArm() {
        val client = ZeusWebSocketClient()
        try {
            assertTrue(client.dryRun)
            val result = client.command(ZeusCommand.Drive(0f, 12, 0f))
            assertFalse(result.accepted)
            assertEquals("DISCONNECTED", result.status)
            val stop = client.command(ZeusCommand.Stop)
            assertFalse(stop.accepted)
            assertEquals("STOP_ATTEMPTED_UNCONFIRMED", stop.status)
            assertEquals(false, stop.data["stop_confirmed"])
        } finally {
            client.close()
        }
    }

    @Test
    fun armGateNeverCarriesArmAcrossConnectOrDisconnect() {
        val gate = ZeusArmGate()
        assertFalse(gate.arm())
        assertFalse(gate.maySendMotion)
        gate.connected()
        assertFalse(gate.maySendMotion)
        assertTrue(gate.arm())
        assertTrue(gate.maySendMotion)
        gate.disconnected()
        assertFalse(gate.maySendMotion)
        gate.connected()
        assertFalse(gate.maySendMotion)
        assertEquals(300L, ZeusWebSocketClient.COMMAND_TTL_MS)
    }
}
