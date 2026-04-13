package com.vantag.agent.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.vantag.agent.MainActivity
import com.vantag.agent.R
import com.vantag.agent.data.api.RetrofitClient
import com.vantag.agent.data.models.AgentStatus
import com.vantag.agent.data.prefs.AppPrefs
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first

class EdgeAgentService : Service() {
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var wakeLock: PowerManager.WakeLock? = null
    private val prefs by lazy { AppPrefs(this) }
    private val cameraWorkers = mutableMapOf<String, CameraWorker>()
    private var heartbeatJob: Job? = null

    companion object {
        private const val TAG = "EdgeAgentService"
        private const val NOTIF_ID = 1001
        const val ACTION_START = "com.vantag.agent.START"
        const val ACTION_STOP = "com.vantag.agent.STOP"

        fun start(context: Context) {
            val intent = Intent(context, EdgeAgentService::class.java).apply {
                action = ACTION_START
            }
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, EdgeAgentService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                startForeground(NOTIF_ID, buildNotification("Starting..."))
                acquireWakeLock()
                startAgent()
            }
            ACTION_STOP -> {
                stopAgent()
                stopSelf()
            }
        }
        return START_STICKY
    }

    private fun startAgent() {
        scope.launch {
            try {
                val config = prefs.agentConfig.first() ?: run {
                    Log.e(TAG, "No agent config found — cannot start")
                    return@launch
                }
                val apiKey = prefs.apiKey.first() ?: return@launch
                val api = RetrofitClient.getInstance(config.backendUrl)

                // Start per-camera workers
                config.cameras.filter { it.enabled }.forEach { cam ->
                    val worker = CameraWorker(
                        cameraConfig = cam,
                        api = api,
                        apiKey = apiKey,
                        onAlert = { event -> showAlertNotification(event.eventType, cam.name) }
                    )
                    cameraWorkers[cam.id] = worker
                    worker.start(scope)
                }

                // Heartbeat loop
                heartbeatJob = scope.launch {
                    while (isActive) {
                        try {
                            val runtime = Runtime.getRuntime()
                            val ramUsed = (runtime.totalMemory() - runtime.freeMemory()) / 1024f / 1024f
                            api.heartbeat(
                                apiKey = apiKey,
                                status = AgentStatus(
                                    deviceId = prefs.agentId.first() ?: "unknown",
                                    online = true,
                                    cameraCount = cameraWorkers.size,
                                    fps = cameraWorkers.values.map { it.currentFps }.average().toFloat(),
                                    cpuPct = 0f,
                                    ramMb = ramUsed,
                                    batteryPct = getBatteryLevel()
                                )
                            )
                        } catch (e: Exception) {
                            Log.w(TAG, "Heartbeat failed: ${e.message}")
                        }
                        delay(30_000)
                    }
                }

                updateNotification("Running — ${cameraWorkers.size} cameras active")
                Log.i(TAG, "Edge agent started with ${cameraWorkers.size} cameras")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start agent: ${e.message}", e)
                updateNotification("Error: ${e.message}")
            }
        }
    }

    private fun stopAgent() {
        heartbeatJob?.cancel()
        cameraWorkers.values.forEach { it.stop() }
        cameraWorkers.clear()
        scope.cancel()
        wakeLock?.release()
        Log.i(TAG, "Edge agent stopped")
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VantagAgent:WakeLock")
        wakeLock?.acquire(6 * 60 * 60 * 1000L) // 6 hours max
    }

    private fun getBatteryLevel(): Int {
        val bm = getSystemService(Context.BATTERY_SERVICE) as? android.os.BatteryManager
        return bm?.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
    }

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, "vantag_agent")
            .setContentTitle("Vantag Edge Agent")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIF_ID, buildNotification(text))
    }

    private fun showAlertNotification(eventType: String, cameraName: String) {
        val title = when (eventType) {
            "sweep" -> "Product Sweep Detected"
            "dwell" -> "Suspicious Loitering"
            "empty_shelf" -> "Empty Shelf Alert"
            "tamper" -> "Camera Tampered"
            else -> "Security Alert"
        }
        val notif = NotificationCompat.Builder(this, "vantag_alerts")
            .setContentTitle(title)
            .setContentText("Camera: $cameraName")
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(System.currentTimeMillis().toInt(), notif)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopAgent()
        super.onDestroy()
    }
}
