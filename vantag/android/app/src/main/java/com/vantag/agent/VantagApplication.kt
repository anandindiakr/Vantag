package com.vantag.agent

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class VantagApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channels = listOf(
                NotificationChannel(
                    "vantag_agent",
                    "Vantag Edge Agent",
                    NotificationManager.IMPORTANCE_LOW
                ).apply { description = "Edge agent running status" },
                NotificationChannel(
                    "vantag_alerts",
                    "Security Alerts",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply { description = "Real-time security detections" }
            )
            val manager = getSystemService(NotificationManager::class.java)
            channels.forEach { manager.createNotificationChannel(it) }
        }
    }
}
