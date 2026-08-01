package com.pulso.app.robot

import com.pulso.app.tools.ActionResult

/** Motor boundary shared by dry-run and physical rover transports. */
interface RoverMotorClient : AutoCloseable {
    val dryRun: Boolean

    suspend fun connect(): ActionResult

    suspend fun arm(operatorPresent: Boolean): ActionResult

    suspend fun disarm(reason: String = "OPERATOR_DISARM"): ActionResult

    suspend fun command(command: ZeusCommand): ActionResult

    fun safetyStatus(): Map<String, Any>
}
