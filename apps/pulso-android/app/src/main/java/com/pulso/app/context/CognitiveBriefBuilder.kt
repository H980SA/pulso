package com.pulso.app.context

import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.WorldState
import kotlin.math.max

class CognitiveBriefBuilder {
    fun build(world: WorldState, cognitive: CognitiveState): String = buildString {
        val robot = world.robot
        appendLine("Mission ${world.mission.id}: ${world.mission.title}")
        appendLine("Mission success means: ${world.mission.successCondition}")
        appendLine("Active goal ${world.activeGoal.id}: ${world.activeGoal.title}")
        appendLine("Active-goal success means: ${world.activeGoal.successCondition}")
        appendLine(
            "Robot is ${robot.motionState.name.lowercase()} at " +
                "(${"%.2f".format(robot.pose.position.x)}, ${"%.2f".format(robot.pose.position.y)})m, " +
                "heading ${robot.pose.headingDeg.toInt()}°, pose confidence ${percent(robot.pose.confidence)}."
        )
        appendLine(
            "VIO ${robot.trackingState.name} at ${percent(robot.trackingQuality)}; " +
                "battery ${percent(robot.batteryFraction)}; flashlight ${if (robot.flashlightOn) "on" else "off"}."
        )
        robot.frontRangeM?.let { appendLine("Nearest forward return is ${"%.2f".format(it)}m.") }
        cognitive.lastActionSummary?.let { appendLine("Last action outcome: $it") }
        world.acousticObservations
            .filter { world.monotonicNowMs <= it.validUntilMonotonicMs }
            .sortedByDescending { it.observedAtMonotonicMs }
            .take(2)
            .forEach { observation ->
                val ageSeconds = max(0L, world.monotonicNowMs - observation.observedAtMonotonicMs) / 1000f
                appendLine(
                    "Acoustic alert ${observation.id}: ${percent(observation.confidence)} intentional-scream candidate, " +
                        "${observation.durationMs}ms, ${"%.1f".format(observation.marginAboveNoiseDb)}dB above local noise, " +
                        "observed ${"%.1f".format(ageSeconds)}s ago. Bearing is unknown: stop and scan visually; " +
                        "do not treat the sound as a localized person."
                )
            }
        world.targets.sortedByDescending { it.possibleHuman }.take(3).forEach { target ->
            val ageSeconds = max(0L, world.monotonicNowMs - target.observedAtMonotonicMs) / 1000f
            val rangeText = target.rangeM?.let { "${"%.1f".format(it)}m away" }
                ?: "range not measured"
            val occlusionText = target.occlusion?.let { "${percent(it)} occluded" }
                ?: "occlusion not measured"
            appendLine(
                "Target ${target.id}: ${percent(target.possibleHuman)} possible human, " +
                    "$rangeText at ${target.bearingDeg.toInt()}°, $occlusionText; " +
                    "observed ${"%.1f".format(ageSeconds)}s ago."
            )
        }
        world.hypotheses.filter { it.goalId == world.activeGoal.id }.forEach { hypothesis ->
            appendLine(
                "Hypothesis ${hypothesis.id} (${percent(hypothesis.confidence)}): ${hypothesis.claim}"
            )
            hypothesis.unresolved.forEach { appendLine("Still unknown: $it") }
        }
        val evidenceRefs = buildSet {
            world.artifacts.forEach { add(it.id) }
            world.targets.forEach { addAll(it.evidenceIds) }
        }.take(12)
        if (evidenceRefs.isNotEmpty()) {
            appendLine("Current evidence refs: ${evidenceRefs.joinToString(", ")}")
        } else {
            appendLine("Current evidence refs: none.")
        }
        appendLine("Agent question: ${cognitive.currentQuestion}")
    }

    private fun percent(value: Float): String = "${(value.coerceIn(0f, 1f) * 100).toInt()}%"
}
