package com.vantag.agent.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Vantag brand colours
val VioletPrimary = Color(0xFF8B5CF6)
val VioletDark = Color(0xFF6D28D9)
val VioletLight = Color(0xFFA78BFA)
val BackgroundDark = Color(0xFF0A0A0F)
val SurfaceDark = Color(0xFF13131A)
val SurfaceVariant = Color(0xFF1E1E2E)
val OnSurface = Color(0xFFE2E8F0)
val OnSurfaceMuted = Color(0xFF64748B)
val ErrorColor = Color(0xFFEF4444)
val SuccessColor = Color(0xFF10B981)
val WarningColor = Color(0xFFF59E0B)

private val DarkColorScheme = darkColorScheme(
    primary = VioletPrimary,
    onPrimary = Color.White,
    primaryContainer = VioletDark,
    onPrimaryContainer = VioletLight,
    secondary = Color(0xFF6366F1),
    background = BackgroundDark,
    surface = SurfaceDark,
    surfaceVariant = SurfaceVariant,
    onBackground = OnSurface,
    onSurface = OnSurface,
    onSurfaceVariant = OnSurfaceMuted,
    error = ErrorColor
)

@Composable
fun VantagTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography(),
        content = content
    )
}
