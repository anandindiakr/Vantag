package com.vantag.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantag.agent.ui.theme.BackgroundDark
import com.vantag.agent.ui.theme.OnSurfaceMuted

@Composable
fun CameraScreen() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundDark),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp)
                    .background(Color(0xFF1E1E2E), RoundedCornerShape(16.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    "Live RTSP stream\ndisplayed here",
                    color = OnSurfaceMuted,
                    textAlign = TextAlign.Center,
                    fontSize = 14.sp
                )
            }
            Spacer(Modifier.height(16.dp))
            Text(
                "Real-time camera feed with bounding box overlays.\nConnect via RTSP URL configured during setup.",
                color = OnSurfaceMuted,
                textAlign = TextAlign.Center,
                fontSize = 13.sp,
                lineHeight = 20.sp
            )
        }
    }
}
