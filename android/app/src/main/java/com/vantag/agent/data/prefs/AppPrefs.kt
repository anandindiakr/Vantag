package com.vantag.agent.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import com.vantag.agent.data.models.AgentConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "vantag_prefs")

class AppPrefs(private val context: Context) {
    private val gson = Gson()

    companion object {
        private val KEY_API_KEY = stringPreferencesKey("api_key")
        private val KEY_AGENT_ID = stringPreferencesKey("agent_id")
        private val KEY_CONFIG = stringPreferencesKey("agent_config")
    }

    val apiKey: Flow<String?> = context.dataStore.data.map { it[KEY_API_KEY] }
    val agentId: Flow<String?> = context.dataStore.data.map { it[KEY_AGENT_ID] }
    val agentConfig: Flow<AgentConfig?> = context.dataStore.data.map { prefs ->
        prefs[KEY_CONFIG]?.let { gson.fromJson(it, AgentConfig::class.java) }
    }

    suspend fun saveApiKey(key: String) = context.dataStore.edit { it[KEY_API_KEY] = key }
    suspend fun saveAgentId(id: String) = context.dataStore.edit { it[KEY_AGENT_ID] = id }
    suspend fun saveConfig(config: AgentConfig) = context.dataStore.edit {
        it[KEY_CONFIG] = gson.toJson(config)
    }

    suspend fun clear() = context.dataStore.edit { it.clear() }
}
