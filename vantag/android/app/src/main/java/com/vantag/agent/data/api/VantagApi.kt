package com.vantag.agent.data.api

import com.vantag.agent.data.models.*
import retrofit2.Response
import retrofit2.http.*

interface VantagApi {

    @POST("api/edge/register")
    suspend fun registerAgent(
        @Body request: RegisterAgentRequest
    ): Response<RegisterAgentResponse>

    @POST("api/edge/events")
    suspend fun postEvent(
        @Header("X-Agent-Key") apiKey: String,
        @Body event: DetectionEvent
    ): Response<Unit>

    @POST("api/edge/heartbeat")
    suspend fun heartbeat(
        @Header("X-Agent-Key") apiKey: String,
        @Body status: AgentStatus
    ): Response<Unit>

    @GET("api/edge/config")
    suspend fun getConfig(
        @Header("X-Agent-Key") apiKey: String
    ): Response<AgentConfig>
}
