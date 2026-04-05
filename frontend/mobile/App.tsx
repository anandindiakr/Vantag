/**
 * App.tsx
 * =======
 * Root component for the Vantag mobile application.
 *
 * Sets up:
 *  - NavigationContainer with bottom tab navigator (Home, Alerts, Cameras,
 *    Watchlist, Settings)
 *  - Push notification permission request on mount
 *  - Background WebSocket initialisation
 *  - Toast provider
 */

import React, { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import Toast from "react-native-toast-message";
import { Ionicons } from "@expo/vector-icons";

// Screens
import HomeScreen from "./src/screens/HomeScreen";
import AlertsScreen from "./src/screens/AlertsScreen";
import CameraScreen from "./src/screens/CameraScreen";
import SettingsScreen from "./src/screens/SettingsScreen";
import StoreDetailScreen from "./src/screens/StoreDetailScreen";

// Hooks
import { useWebSocket } from "./src/hooks/useWebSocket";
import { usePushNotifications } from "./src/hooks/usePushNotifications";
import { useMobileStore } from "./src/store/useMobileStore";

// ─── Navigation Types ────────────────────────────────────────────────────────

export type RootTabParamList = {
  Home: undefined;
  Alerts: undefined;
  Cameras: undefined;
  Settings: undefined;
};

export type HomeStackParamList = {
  StoreList: undefined;
  StoreDetail: { storeId: string; storeName: string };
};

const Tab = createBottomTabNavigator<RootTabParamList>();
const HomeStack = createNativeStackNavigator<HomeStackParamList>();

// ─── Home Stack (stores list + detail) ───────────────────────────────────────

function HomeNavigator() {
  return (
    <HomeStack.Navigator>
      <HomeStack.Screen
        name="StoreList"
        component={HomeScreen}
        options={{ title: "Stores" }}
      />
      <HomeStack.Screen
        name="StoreDetail"
        component={StoreDetailScreen}
        options={({ route }) => ({ title: route.params.storeName })}
      />
    </HomeStack.Navigator>
  );
}

// ─── Watchlist placeholder ────────────────────────────────────────────────────

function WatchlistScreen() {
  const { View: V, Text } = require("react-native");
  return (
    <V style={styles.placeholder}>
      <Text style={styles.placeholderText}>Watchlist</Text>
    </V>
  );
}

// ─── WebSocket initialiser component ────────────────────────────────────────

function WebSocketInit() {
  const backendUrl = useMobileStore((s) => s.settings.backendUrl);
  useWebSocket(backendUrl);
  return null;
}

// ─── Root App ────────────────────────────────────────────────────────────────

export default function App() {
  const { requestPermissions } = usePushNotifications();
  const recentEvents = useMobileStore((s) => s.recentEvents);

  // Count unread HIGH severity events
  const unreadHighCount = recentEvents.filter(
    (e) => e.severity === "HIGH" && !e.read
  ).length;

  useEffect(() => {
    requestPermissions();
  }, []);

  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      <WebSocketInit />
      <NavigationContainer>
        <Tab.Navigator
          screenOptions={({ route }: { route: { name: string } }) => ({
            headerShown: false,
            tabBarActiveTintColor: "#2563EB",
            tabBarInactiveTintColor: "#9CA3AF",
            tabBarStyle: {
              backgroundColor: "#FFFFFF",
              borderTopColor: "#E5E7EB",
              elevation: 8,
              shadowOpacity: 0.1,
            },
            tabBarIcon: ({ focused, color, size }: { focused: boolean; color: string; size: number }) => {
              const icons: Record<string, keyof typeof Ionicons.glyphMap> = {
                Home: focused ? "storefront" : "storefront-outline",
                Alerts: focused ? "notifications" : "notifications-outline",
                Cameras: focused ? "videocam" : "videocam-outline",
                Settings: focused ? "settings" : "settings-outline",
              };
              return (
                <Ionicons
                  name={icons[route.name] ?? "ellipse-outline"}
                  size={size}
                  color={color}
                />
              );
            },
          })}
        >
          <Tab.Screen
            name="Home"
            component={HomeNavigator}
            options={{ title: "Stores" }}
          />
          <Tab.Screen
            name="Alerts"
            component={AlertsScreen}
            options={{
              title: "Alerts",
              tabBarBadge: unreadHighCount > 0 ? unreadHighCount : undefined,
              tabBarBadgeStyle: { backgroundColor: "#DC2626" },
            }}
          />
          <Tab.Screen
            name="Cameras"
            component={CameraScreen}
            options={{ title: "Cameras" }}
          />
          <Tab.Screen
            name="Settings"
            component={SettingsScreen}
            options={{ title: "Settings" }}
          />
        </Tab.Navigator>
      </NavigationContainer>
      <Toast />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  placeholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F9FAFB",
  },
  placeholderText: {
    fontSize: 18,
    color: "#6B7280",
  },
});
