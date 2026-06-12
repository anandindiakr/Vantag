package com.vantag.agent.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantag.agent.data.models.CameraUiState
import com.vantag.agent.ui.theme.OnSurfaceMuted
import com.vantag.agent.ui.theme.SurfaceVariant

@Composable
fun CameraCard(
    cameraState: CameraUiState,
    modifier: Modifier = Modifier
) {
    val cam = cameraState.config
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceVariant)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(44.dp)
                        .background(
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                            RoundedCornerShape(12.dp)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Default.Videocam,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(22.dp)
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(cam.name, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                    Text(cam.location.ifEmpty { "No location set" }, color = OnSurfaceMuted, fontSize = 12.sp)
                }
                StatusBadge(isOnline = cameraState.isConnected)
            }

            Spacer(modifier = Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                StatChip("FPS", "${cameraState.fps.toInt()}")
                cameraState.lastEvent?.let {
                    EventBadge(it.eventType)
                }
            }

            cameraState.errorMsg?.let { err ->
                Spacer(modifier = Modifier.height(8.dp))
                Text(err, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun StatChip(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(label, color = OnSurfaceMuted, fontSize = 11.sp)
    }
}
