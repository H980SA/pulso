package com.pulso.app.context

import com.pulso.app.domain.Candidate
import com.pulso.app.domain.CandidateKind
import com.pulso.app.domain.CognitiveState
import com.pulso.app.domain.DecisionNeed
import com.pulso.app.domain.MissionCheckpoint
import com.pulso.app.domain.VisualView
import com.pulso.app.domain.WorldPacket
import com.pulso.app.domain.WorldState

class ContextSelector(
    private val briefBuilder: CognitiveBriefBuilder = CognitiveBriefBuilder(),
) {
    fun select(
        world: WorldState,
        need: DecisionNeed,
        cognitive: CognitiveState,
        checkpoint: MissionCheckpoint,
        requestedVisual: VisualView? = null,
    ): WorldPacket {
        val candidates = world.candidates
            .asSequence()
            .filter { isValid(it, world) }
            .filter { candidateMatchesNeed(it, need) }
            .sortedWith(compareByDescending<Candidate> { it.informationGain }.thenBy { it.risk })
            .take(MAX_CANDIDATES)
            .toList()

        val visual = requestedVisual?.takeIf {
            need.requiresVisualView &&
                it.requestActionId.isNotBlank() &&
                it.jpegBytes?.isNotEmpty() == true &&
                it.navigationRevision == world.navigationRevision &&
                visualMatchesNeed(it, need, world)
        }
        return WorldPacket(
            worldSeq = world.worldSeq,
            decisionNeed = need,
            brief = briefBuilder.build(world, cognitive),
            candidates = candidates,
            visualView = visual,
            checkpoint = checkpoint,
            cognitiveState = cognitive,
        )
    }

    fun isValid(candidate: Candidate, world: WorldState): Boolean {
        if (world.monotonicNowMs > candidate.validUntilMonotonicMs) return false
        if (world.robot.trackingEpoch != candidate.trackingEpoch) return false
        if (candidate.navigationRevision != world.navigationRevision) return false
        if (candidate.id.kind in setOf(CandidateKind.FRONTIER, CandidateKind.VIEWPOINT, CandidateKind.TARGET) &&
            candidate.capability.length < MIN_NAVIGATION_GRANT_LENGTH
        ) return false
        if (candidate.id.kind == CandidateKind.TARGET) {
            val targetRevision = candidate.targetRevision ?: return false
            val targetId = candidate.id.value.substringBefore(':')
            val currentRevision = world.targets.firstOrNull { it.id == targetId }?.revision
            if (currentRevision != targetRevision) return false
        }
        return true
    }

    private fun candidateMatchesNeed(candidate: Candidate, need: DecisionNeed): Boolean = when (need) {
        DecisionNeed.MONITOR -> candidate.id.kind != CandidateKind.VIEWPOINT
        DecisionNeed.CHOOSE_ROUTE -> candidate.id.kind in setOf(CandidateKind.VIEWPOINT, CandidateKind.FRONTIER)
        DecisionNeed.INSPECT_TARGET -> candidate.id.kind in setOf(CandidateKind.VIEWPOINT, CandidateKind.TARGET)
        DecisionNeed.RECOVER_TRACKING -> candidate.id.kind == CandidateKind.ANCHOR
    }

    private fun visualMatchesNeed(
        view: VisualView,
        need: DecisionNeed,
        world: WorldState,
    ): Boolean = when (need) {
        DecisionNeed.CHOOSE_ROUTE -> view.kind == "META_VIEW"
        DecisionNeed.INSPECT_TARGET -> {
            val candidate = world.candidates.firstOrNull { it.id == view.targetId }
            view.kind in setOf("CANDIDATE_VIEW", "TARGET_VIEW") &&
                candidate != null && candidate.targetRevision == view.targetRevision
        }
        else -> false
    }

    private companion object {
        const val MAX_CANDIDATES = 5
        const val MIN_NAVIGATION_GRANT_LENGTH = 16
    }
}
