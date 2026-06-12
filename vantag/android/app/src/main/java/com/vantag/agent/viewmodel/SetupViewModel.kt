package com.vantag.agent.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vantag.agent.data.api.RetrofitClient
import com.vantag.agent.data.models.RegisterAgentRequest
import com.vantag.agent.data.prefs.AppPrefs
import com.vantag.agent.service.EdgeAgentService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

sealed class SetupState {
    data object Idle : SetupState()
    data object Loading : SetupState()
    data object Success : SetupState()
    data class Error(val message: String) : SetupState()
}

class SetupViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = AppPrefs(app)
    private val _state = MutableStateFlow<SetupState>(SetupState.Idle)
    val state: StateFlow<SetupState> = _state

    private val _isConfigured = MutableStateFlow(false)
    val isConfigured: StateFlow<Boolean> = _isConfigured

    init {
        viewModelScope.launch {
            val key = prefs.apiKey.first()
            _isConfigured.value = !key.isNullOrBlank()
        }
    }

    /**
     * Called after user scans QR code or manually enters API key.
     * Registers device with backend and saves config.
     */
    fun registerWithApiKey(apiKey: String, backendUrl: String) {
        _state.value = SetupState.Loading
        viewModelScope.launch {
            try {
                val normalizedUrl = if (backendUrl.endsWith("/")) backendUrl else "$backendUrl/"
                val api = RetrofitClient.getInstance(normalizedUrl)
                val response = api.registerAgent(RegisterAgentRequest(apiKey = apiKey))

                if (response.isSuccessful) {
                    val body = response.body()!!
                    prefs.saveApiKey(apiKey)
                    prefs.saveAgentId(body.agentId)
                    prefs.saveConfig(body.config)

                    // Start the foreground service
                    EdgeAgentService.start(getApplication())
                    _isConfigured.value = true
                    _state.value = SetupState.Success
                    Log.i("SetupVM", "Registered agent ${body.agentId} with ${body.config.cameras.size} cameras")
                } else {
                    _state.value = SetupState.Error("Server error: ${response.code()} — ${response.errorBody()?.string()}")
                }
            } catch (e: Exception) {
                _state.value = SetupState.Error("Connection failed: ${e.message}")
                Log.e("SetupVM", "Registration error", e)
            }
        }
    }

    fun resetSetup() {
        viewModelScope.launch {
            EdgeAgentService.stop(getApplication())
            prefs.clear()
            _isConfigured.value = false
            _state.value = SetupState.Idle
        }
    }
}
