package com.pulso.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Approved PULSO field-console palette: paper, ink and one operational orange.
// The same semantic names are mirrored by Mission Control's CSS tokens.
val PulsoInk = Color(0xFF171717)
val PulsoMuted = Color(0xFF66645F)
val PulsoFaint = Color(0xFF96938C)
val PulsoBackground = Color(0xFFFAF9F6)
val PulsoPanel = Color(0xFFFFFFFF)
val PulsoPanelRaised = Color(0xFFF2F0EB)
val PulsoBorder = Color(0xFFD8D5CF)
val PulsoBorderStrong = Color(0xFFAAA69E)
val PulsoCyan = Color(0xFF159DB5)
val PulsoOrange = Color(0xFFFF4E18)
val PulsoYellow = Color(0xFFEAAE16)
val PulsoMagenta = Color(0xFFD72CA7)
val PulsoGreen = Color(0xFF238B45)
val PulsoRed = Color(0xFFD92D20)

private val PulsoColors = lightColorScheme(
    primary = PulsoOrange,
    secondary = PulsoGreen,
    tertiary = PulsoCyan,
    background = PulsoBackground,
    surface = PulsoPanel,
    onPrimary = Color.White,
    onBackground = PulsoInk,
    onSurface = PulsoInk,
    outline = PulsoBorder,
    outlineVariant = PulsoBorderStrong,
    error = PulsoRed,
    onError = Color.White,
)

@Composable
fun PulsoTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = PulsoColors, content = content)
}
