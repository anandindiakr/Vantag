package com.vantag.agent.data.models

import com.google.gson.annotations.SerializedName

data class AgentConfig(
    @SerializedName("api_key") val apiKey: String,
    @SerializedName("tenant_id") val tenantId: String,
    @SerializedName("backend_url") val backendUrl: String,
    @SerializedName("mqtt_host") val mqttHost: String,
    @SerializedName("mqtt_port") val mqttPort: Int = 1883,
    @SerializedName("cameras") val cameras: List<CameraConfig>
)

data class CameraConfig(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String,
    @SerializedName("rtsp_url") val rtspUrl: String,
    @SerializedName("location") val location: String = "",
    @SerializedName("enabled") val enabled: Boolean = true
)

data class DetectionEvent(
    @SerializedName("camera_id") val cameraId: String,
    @SerializedName("event_type") val eventType: String,   // "sweep" | "dwell" | "empty_shelf" | "tamper"
    @SerializedName("confidence") val confidence: Float,
    @SerializedName("timestamp") val timestamp: Long = System.currentTimeMillis(),
    @SerializedName("thumbnail_b64") val thumbnailB64: String? = null,
    @SerializedName("bounding_boxes") val boundingBoxes: List<BoundingBox> = emptyList()
)

data class BoundingBox(
    @SerializedName("x") val x: Float,
    @SerializedName("y") val y: Float,
    @SerializedName("w") val w: Float,
    @SerializedName("h") val h: Float,
    @SerializedName("label") val label: String
)

data class AgentStatus(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("online") val online: Boolean,
    @SerializedName("camera_count") val cameraCount: Int,
    @SerializedName("fps") val fps: Float,
    @SerializedName("cpu_pct") val cpuPct: Float,
    @SerializedName("ram_mb") val ramMb: Float,
    @SerializedName("battery_pct") val batteryPct: Int
)

data class RegisterAgentRequest(
    @SerializedName("api_key") val apiKey: String,
    @SerializedName("device_type") val deviceType: String = "android",
    @SerializedName("device_model") val deviceModel: String = android.os.Build.MODEL,
    @SerializedName("os_version") val osVersion: String = android.os.Build.VERSION.RELEASE
)

data class RegisterAgentResponse(
    @SerializedName("agent_id") val agentId: String,
    @SerializedName("config") val config: AgentConfig
)

// UI state helpers
data class CameraUiState(
    val config: CameraConfig,
    val isConnected: Boolean = false,
    val fps: Float = 0f,
    val lastEvent: DetectionEvent? = null,
    val errorMsg: String? = null
)
