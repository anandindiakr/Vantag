package com.vantag.agent.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vantag.agent.data.models.AgentConfig
import com.vantag.agent.data.models.CameraUiState
import com.vantag.agent.data.prefs.AppPrefs
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class DashboardViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = AppPrefs(app)

    val agentConfig: StateFlow<AgentConfig?> = prefs.agentConfig
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    private val _cameras = MutableStateFlow<List<CameraUiState>>(emptyList())
    val cameras: StateFlow<List<CameraUiState>> = _cameras

    private val _serviceRunning = MutableStateFlow(false)
    val serviceRunning: StateFlow<Boolean> = _serviceRunning

    init {
        viewModelScope.launch {
            agentConfig.collect { config ->
                if (config != null) {
                    _cameras.value = config.cameras.map { CameraUiState(config = it) }
                }
            }
        }
    }

    fun toggleService(running: Boolean) {
        _serviceRunning.value = running
        if (running) {
            com.vantag.agent.service.EdgeAgentService.start(getApplication())
        } else {
            com.vantag.agent.service.EdgeAgentService.stop(getApplication())
        }
    }
}
