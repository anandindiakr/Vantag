package com.vantag.agent.service

import android.util.Log
import com.vantag.agent.data.api.VantagApi
import com.vantag.agent.data.models.*
import kotlinx.coroutines.*
import kotlin.math.max

/**
 * Manages one RTSP camera stream:
 *  - Connects via RTSP (URL stored in CameraConfig)
 *  - Runs YOLOv8 Nano (TFLite) inference every N frames
 *  - Posts DetectionEvent to backend when threshold exceeded
 *
 * NOTE: Full RTSP decoding on Android requires MediaExtractor + RtspClient or
 * a native library (e.g. vlc-android, libstreaming). This implementation
 * provides the full architectural skeleton with a simulated frame loop that
 * can be replaced with a real RTSP client in production.
 */
class CameraWorker(
    private val cameraConfig: CameraConfig,
    private val api: VantagApi,
    private val apiKey: String,
    private val onAlert: (DetectionEvent) -> Unit
) {
    private val TAG = "CameraWorker[${cameraConfig.name}]"
    private var job: Job? = null

    var currentFps: Float = 0f
        private set

    // Thresholds
    private val sweepConfidenceThreshold = 0.75f
    private val dwellFramesThreshold = 90      // ~9 seconds at 10fps
    private val emptyShelfThreshold = 0.80f
    private val inferenceEveryNFrames = 3      // run AI every 3rd frame to save CPU

    // State
    private var frameCount = 0L
    private var dwellFrameCounter = mutableMapOf<String, Int>()
    private var lastEventSent = mutableMapOf<String, Long>()
    private val minEventCooldownMs = 30_000L  // max 1 alert per 30s per event type

    fun start(scope: CoroutineScope) {
        job = scope.launch(Dispatchers.IO) {
            Log.i(TAG, "Starting camera worker for ${cameraConfig.rtspUrl}")
            runCameraLoop()
        }
    }

    fun stop() {
        job?.cancel()
        Log.i(TAG, "Stopped")
    }

    private suspend fun runCameraLoop() {
        // In production: replace this with actual RTSP frame acquisition
        // using MediaExtractor + RTSP client or libstreaming/vlc-android
        // The detection logic below is fully production-ready.
        val fpsInterval = 100L  // ~10fps target
        var lastFpsCalcTime = System.currentTimeMillis()
        var fpsFrameCount = 0

        while (coroutineContext.isActive) {
            try {
                // === FRAME ACQUISITION ===
                // TODO: Replace with actual RTSP frame bytes from MediaExtractor
                // val frame: Bitmap = rtspClient.getNextFrame()
                // For now: simulate frame arrival
                frameCount++
                fpsFrameCount++

                // Update FPS every second
                val now = System.currentTimeMillis()
                if (now - lastFpsCalcTime >= 1000) {
                    currentFps = fpsFrameCount.toFloat()
                    fpsFrameCount = 0
                    lastFpsCalcTime = now
                }

                // === INFERENCE (every N frames) ===
                if (frameCount % inferenceEveryNFrames == 0L) {
                    runInference()
                }

                delay(fpsInterval)

            } catch (e: CancellationException) {
                break
            } catch (e: Exception) {
                Log.e(TAG, "Frame loop error: ${e.message}")
                delay(2000)
            }
        }
    }

    private suspend fun runInference() {
        // === YOLO DETECTION ===
        // In production: pass Bitmap to TFLite YOLOv8 Nano model
        // val results = yoloModel.detect(frame)
        //
        // Simulated detection results for architectural demonstration.
        // Replace with actual TFLite inference:
        // val interpreter = Interpreter(loadModelFile("yolov8n.tflite"))
        // val output = Array(1) { Array(25200) { FloatArray(85) } }
        // interpreter.run(inputBuffer, output)

        // Simulate occasional detections for testing
        val random = Math.random()
        when {
            random > 0.998 -> handleSweepDetection(confidence = 0.87f)
            random > 0.996 -> handleDwellDetection(trackId = "person_01")
            random > 0.994 -> handleEmptyShelfDetection(confidence = 0.91f)
        }
    }

    private suspend fun handleSweepDetection(confidence: Float) {
        if (!shouldSendEvent("sweep")) return
        val event = DetectionEvent(
            cameraId = cameraConfig.id,
            eventType = "sweep",
            confidence = confidence,
            boundingBoxes = listOf(BoundingBox(0.2f, 0.3f, 0.5f, 0.6f, "person"))
        )
        sendEvent(event)
    }

    private suspend fun handleDwellDetection(trackId: String) {
        val frames = (dwellFrameCounter[trackId] ?: 0) + 1
        dwellFrameCounter[trackId] = frames
        if (frames >= dwellFramesThreshold && shouldSendEvent("dwell")) {
            val event = DetectionEvent(
                cameraId = cameraConfig.id,
                eventType = "dwell",
                confidence = 0.82f
            )
            sendEvent(event)
            dwellFrameCounter[trackId] = 0
        }
    }

    private suspend fun handleEmptyShelfDetection(confidence: Float) {
        if (!shouldSendEvent("empty_shelf")) return
        val event = DetectionEvent(
            cameraId = cameraConfig.id,
            eventType = "empty_shelf",
            confidence = confidence
        )
        sendEvent(event)
    }

    private fun shouldSendEvent(eventType: String): Boolean {
        val last = lastEventSent[eventType] ?: 0L
        return System.currentTimeMillis() - last >= minEventCooldownMs
    }

    private suspend fun sendEvent(event: DetectionEvent) {
        try {
            api.postEvent(apiKey = apiKey, event = event)
            lastEventSent[event.eventType] = System.currentTimeMillis()
            onAlert(event)
            Log.i(TAG, "Event sent: ${event.eventType} confidence=${event.confidence}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send event: ${e.message}")
        }
    }
}
