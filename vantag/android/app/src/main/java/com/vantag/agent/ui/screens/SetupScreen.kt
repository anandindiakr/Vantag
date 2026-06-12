package com.vantag.agent.ui.screens

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantag.agent.ui.theme.*
import com.vantag.agent.viewmodel.SetupState
import com.vantag.agent.viewmodel.SetupViewModel

@Composable
fun SetupScreen(viewModel: SetupViewModel) {
    val state by viewModel.state.collectAsState()
    var apiKey by remember { mutableStateOf("") }
    var backendUrl by remember { mutableStateOf("https://app.vantag.io") }
    var showManual by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(BackgroundDark, Color(0xFF0D0D1A))
                )
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Logo
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .background(
                        Brush.linearGradient(listOf(VioletPrimary, Color(0xFF6366F1))),
                        RoundedCornerShape(20.dp)
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Shield, contentDescription = null,
                    tint = Color.White, modifier = Modifier.size(36.dp))
            }

            Spacer(Modifier.height(24.dp))
            Text("Vantag Edge Agent", fontSize = 26.sp, fontWeight = FontWeight.ExtraBold)
            Text("Connect your cameras to Vantag",
                color = OnSurfaceMuted, fontSize = 14.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp, bottom = 40.dp)
            )

            // QR Scan option
            OutlinedButton(
                onClick = { /* TODO: Launch camera for QR scan */ },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = VioletPrimary)
            ) {
                Text("📷  Scan QR Code from Dashboard", fontSize = 15.sp)
            }

            Spacer(Modifier.height(12.dp))

            TextButton(onClick = { showManual = !showManual }) {
                Text(
                    if (showManual) "Hide manual entry" else "Enter API key manually",
                    color = OnSurfaceMuted
                )
            }

            AnimatedVisibility(showManual) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = backendUrl,
                        onValueChange = { backendUrl = it },
                        label = { Text("Backend URL") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
                    )
                    OutlinedTextField(
                        value = apiKey,
                        onValueChange = { apiKey = it },
                        label = { Text("API Key") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        placeholder = { Text("vantag_agt_...") }
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            if (showManual) {
                Button(
                    onClick = { viewModel.registerWithApiKey(apiKey.trim(), backendUrl.trim()) },
                    enabled = apiKey.length > 10 && backendUrl.isNotBlank() && state !is SetupState.Loading,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = VioletPrimary)
                ) {
                    if (state is SetupState.Loading) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                    } else {
                        Text("Connect Agent", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }

            AnimatedVisibility(state is SetupState.Error) {
                val msg = (state as? SetupState.Error)?.message ?: ""
                Card(
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    colors = CardDefaults.cardColors(containerColor = ErrorColor.copy(alpha = 0.15f)),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(msg, color = ErrorColor,
                        modifier = Modifier.padding(12.dp), fontSize = 13.sp)
                }
            }
        }
    }
}
