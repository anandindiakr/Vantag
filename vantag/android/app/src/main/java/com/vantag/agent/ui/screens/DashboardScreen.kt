package com.vantag.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantag.agent.ui.components.CameraCard
import com.vantag.agent.ui.components.StatusBadge
import com.vantag.agent.ui.theme.*
import com.vantag.agent.viewmodel.DashboardViewModel
import com.vantag.agent.viewmodel.SetupViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    dashboardViewModel: DashboardViewModel,
    setupViewModel: SetupViewModel
) {
    val config by dashboardViewModel.agentConfig.collectAsState()
    val cameras by dashboardViewModel.cameras.collectAsState()
    val serviceRunning by dashboardViewModel.serviceRunning.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(
                            modifier = Modifier
                                .size(30.dp)
                                .background(
                                    Brush.linearGradient(listOf(VioletPrimary, Color(0xFF6366F1))),
                                    RoundedCornerShape(8.dp)
                                ),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.Shield, null, tint = Color.White, modifier = Modifier.size(16.dp))
                        }
                        Text("Vantag Agent", fontWeight = FontWeight.Bold)
                    }
                },
                actions = {
                    StatusBadge(isOnline = serviceRunning, modifier = Modifier.padding(end = 8.dp))
                    IconButton(onClick = { setupViewModel.resetSetup() }) {
                        Icon(Icons.Default.Logout, contentDescription = "Reset", tint = OnSurfaceMuted)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SurfaceDark)
            )
        },
        containerColor = BackgroundDark
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // Status Card
            item {
                Card(
                    shape = RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = VioletPrimary.copy(alpha = if (serviceRunning) 0.12f else 0.05f)
                    )
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(20.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                if (serviceRunning) "Agent Running" else "Agent Stopped",
                                fontWeight = FontWeight.Bold, fontSize = 18.sp
                            )
                            Text(
                                "${cameras.size} cameras configured",
                                color = OnSurfaceMuted, fontSize = 13.sp
                            )
                            config?.tenantId?.let {
                                Text("Tenant: ${it.take(8)}...", color = OnSurfaceMuted, fontSize = 11.sp)
                            }
                        }
                        Switch(
                            checked = serviceRunning,
                            onCheckedChange = { dashboardViewModel.toggleService(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = VioletPrimary
                            )
                        )
                    }
                }
            }

            // Camera list header
            item {
                Text("Cameras", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = OnSurfaceMuted,
                    modifier = Modifier.padding(top = 4.dp))
            }

            if (cameras.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(40.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.Videocam, null, tint = OnSurfaceMuted, modifier = Modifier.size(40.dp))
                            Spacer(Modifier.height(8.dp))
                            Text("No cameras configured", color = OnSurfaceMuted)
                            Text("Complete setup on the web dashboard", color = OnSurfaceMuted, fontSize = 12.sp)
                        }
                    }
                }
            } else {
                items(cameras, key = { it.config.id }) { cam ->
                    CameraCard(cameraState = cam)
                }
            }
        }
    }
}
