/**
 * src/hooks/usePushNotifications.ts
 * ===================================
 * Expo push notification hook for the Vantag mobile app.
 *
 * Features:
 *  - Request notification permissions via expo-notifications
 *  - Register device Expo push token with backend (POST /api/devices/register)
 *  - Handle foreground notifications (display in-app toast)
 *  - Handle notification response (tap) → navigate to relevant screen
 */

import { useEffect, useRef, useCallback } from "react";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { useNavigation } from "@react-navigation/native";
import axios from "axios";

import { useMobileStore } from "../store/useMobileStore";

// ─── Notification handler (foreground) ───────────────────────────────────────
// Display alert + badge + sound when app is open

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

// ─── usePushNotifications ─────────────────────────────────────────────────────

export function usePushNotifications() {
  const notificationListener = useRef<Notifications.Subscription | null>(null);
  const responseListener = useRef<Notifications.Subscription | null>(null);

  const settings = useMobileStore((s) => s.settings);

  // Navigation reference (may be undefined if hook is called outside navigator)
  let navigation: ReturnType<typeof useNavigation> | null = null;
  try {
    navigation = useNavigation();
  } catch {
    // Outside NavigationContainer — skip navigation on tap
  }

  // ── Request permissions & register token ────────────────────────────────────

  const requestPermissions = useCallback(async () => {
    if (!settings.pushNotificationsEnabled) return;

    try {
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      if (existingStatus !== "granted") {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }

      if (finalStatus !== "granted") {
        console.warn("[PushNotifications] Permission not granted.");
        return;
      }

      // Android channel setup
      if (Platform.OS === "android") {
        await Notifications.setNotificationChannelAsync("vantag-alerts", {
          name: "Vantag Alerts",
          importance: Notifications.AndroidImportance.HIGH,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: "#EF4444",
          sound: "default",
        });
      }

      // Retrieve Expo push token
      const tokenData = await Notifications.getExpoPushTokenAsync();
      const token = tokenData.data;

      // Register with backend
      try {
        await axios.post(
          `${settings.backendUrl}/api/devices/register`,
          {
            token,
            platform: Platform.OS,
            app_version: "2.0.0",
          },
          { timeout: 8000 }
        );
      } catch (err) {
        // Non-fatal — backend may not have this endpoint yet
        console.warn("[PushNotifications] Token registration failed:", err);
      }
    } catch (err) {
      console.warn("[PushNotifications] Setup error:", err);
    }
  }, [settings.pushNotificationsEnabled, settings.backendUrl]);

  // ── Foreground notification listener ────────────────────────────────────────

  useEffect(() => {
    // Foreground: display toast
    notificationListener.current =
      Notifications.addNotificationReceivedListener((notification) => {
        const { title, body } = notification.request.content;
        // We rely on expo-notifications to show the system banner (configured above)
        // Additional in-app toast can be added here via react-native-toast-message
        console.info(
          "[PushNotifications] Foreground notification received:",
          title,
          body
        );
      });

    // Response: user tapped notification
    responseListener.current =
      Notifications.addNotificationResponseReceivedListener((response) => {
        const data =
          (response.notification.request.content.data as Record<string, unknown>) ?? {};

        const screen = data.screen as string | undefined;
        const storeId = data.store_id as string | undefined;
        const storeName = data.store_name as string | undefined;

        if (!navigation) return;

        // Navigate to relevant screen based on data payload
        try {
          if (screen === "alerts") {
            (navigation as any).navigate("Alerts");
          } else if (screen === "store_detail" && storeId) {
            (navigation as any).navigate("Home", {
              screen: "StoreDetail",
              params: { storeId, storeName: storeName ?? storeId },
            });
          } else {
            // Default: go to Alerts tab
            (navigation as any).navigate("Alerts");
          }
        } catch {
          // Navigation may not be ready
        }
      });

    return () => {
      if (notificationListener.current) {
        Notifications.removeNotificationSubscription(
          notificationListener.current
        );
      }
      if (responseListener.current) {
        Notifications.removeNotificationSubscription(responseListener.current);
      }
    };
  }, [navigation]);

  return { requestPermissions };
}
