package com.pulso.app.tools

import android.content.Context

data class SkillDescriptor(
    val id: String,
    val whenUseful: String,
)

data class LoadedSkill(
    val id: String,
    val whenUseful: String,
    val instructions: String,
)

class SkillLibrary(private val context: Context) {
    private val descriptors = listOf(
        SkillDescriptor("survivor_inspection", "A possible person is visible but evidence is incomplete."),
        SkillDescriptor("darkness_recovery", "Vision confidence falls because the scene is dark or backlit."),
        SkillDescriptor("vio_recovery", "Tracking is LIMITED or LOST and a safe relocalization is needed."),
    )

    fun catalog(): List<SkillDescriptor> = descriptors

    fun load(id: String): LoadedSkill? {
        val descriptor = descriptors.firstOrNull { it.id == id } ?: return null
        val instructions = context.assets.open("skills/$id.md").bufferedReader().use { it.readText() }
        return LoadedSkill(id, descriptor.whenUseful, instructions)
    }
}
