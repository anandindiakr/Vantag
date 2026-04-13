package com.vantag.agent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.*
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.vantag.agent.ui.screens.DashboardScreen
import com.vantag.agent.ui.screens.SetupScreen
import com.vantag.agent.ui.theme.VantagTheme
import com.vantag.agent.viewmodel.DashboardViewModel
import com.vantag.agent.viewmodel.SetupViewModel

class MainActivity : ComponentActivity() {
    private val setupViewModel: SetupViewModel by viewModels()
    private val dashboardViewModel: DashboardViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            VantagTheme {
                VantagNavGraph(setupViewModel, dashboardViewModel)
            }
        }
    }
}

@Composable
fun VantagNavGraph(
    setupViewModel: SetupViewModel,
    dashboardViewModel: DashboardViewModel
) {
    val navController = rememberNavController()
    val isConfigured by setupViewModel.isConfigured.collectAsState()

    val startDest = if (isConfigured) "dashboard" else "setup"

    NavHost(navController = navController, startDestination = startDest) {
        composable("setup") {
            SetupScreen(viewModel = setupViewModel)
            LaunchedEffect(isConfigured) {
                if (isConfigured) navController.navigate("dashboard") {
                    popUpTo("setup") { inclusive = true }
                }
            }
        }
        composable("dashboard") {
            DashboardScreen(
                dashboardViewModel = dashboardViewModel,
                setupViewModel = setupViewModel
            )
            LaunchedEffect(!isConfigured) {
                if (!isConfigured) navController.navigate("setup") {
                    popUpTo("dashboard") { inclusive = true }
                }
            }
        }
    }
}
