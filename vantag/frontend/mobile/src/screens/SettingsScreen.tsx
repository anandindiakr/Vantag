/**
 * src/screens/SettingsScreen.tsx
 * ================================
 * App settings screen.
 *
 * Features:
 *  - TextInput for backend URL
 *  - TextInput for MQTT broker URL
 *  - Toggle for push notifications
 *  - "Test Connection" button → calls /health endpoint
 *  - App version display
 */

import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Switch,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import axios from "axios";

import { useMobileStore } from "../store/useMobileStore";

// ─── Package version (inline — no native module required) ─────────────────────
const APP_VERSION = "2.0.0";

// ─── Section wrapper ─────────────────────────────────────────────────────────

function SettingsSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

// ─── Labeled text input ───────────────────────────────────────────────────────

function SettingsInput({
  label,
  value,
  placeholder,
  onChangeText,
  keyboardType = "default",
  autoCapitalize = "none",
}: {
  label: string;
  value: string;
  placeholder: string;
  onChangeText: (v: string) => void;
  keyboardType?: "default" | "url" | "numeric";
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
}) {
  return (
    <View style={styles.inputGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        placeholder={placeholder}
        placeholderTextColor="#9CA3AF"
        onChangeText={onChangeText}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        clearButtonMode="while-editing"
      />
    </View>
  );
}

// ─── SettingsScreen ───────────────────────────────────────────────────────────

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();

  const settings = useMobileStore((s) => s.settings);
  const updateSettings = useMobileStore((s) => s.updateSettings);

  const [backendUrl, setBackendUrl] = useState(settings.backendUrl);
  const [mqttUrl, setMqttUrl] = useState(settings.mqttBrokerUrl);
  const [pushEnabled, setPushEnabled] = useState(
    settings.pushNotificationsEnabled
  );

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [saved, setSaved] = useState(false);

  // ── Save settings ───────────────────────────────────────────────────────────

  const handleSave = () => {
    updateSettings({
      backendUrl: backendUrl.trim().replace(/\/$/, ""),
      mqttBrokerUrl: mqttUrl.trim(),
      pushNotificationsEnabled: pushEnabled,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  // ── Test connection ─────────────────────────────────────────────────────────

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const url = backendUrl.trim().replace(/\/$/, "");
    try {
      const res = await axios.get<{ status: string; version: string; uptime_seconds: number }>(
        `${url}/health`,
        { timeout: 6000 }
      );
      setTestResult({
        ok: true,
        message: `Connected ✓  v${res.data.version} · uptime ${Math.round(res.data.uptime_seconds)}s`,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Connection failed";
      setTestResult({ ok: false, message: msg });
    } finally {
      setTesting(false);
    }
  };

  // ── Reset to defaults ───────────────────────────────────────────────────────

  const handleReset = () => {
    Alert.alert(
      "Reset settings",
      "Restore all settings to their defaults?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reset",
          style: "destructive",
          onPress: () => {
            const defaults = {
              backendUrl: "http://192.168.1.10:8000",
              mqttBrokerUrl: "ws://192.168.1.10:9001",
              pushNotificationsEnabled: true,
            };
            setBackendUrl(defaults.backendUrl);
            setMqttUrl(defaults.mqttBrokerUrl);
            setPushEnabled(defaults.pushNotificationsEnabled);
            updateSettings(defaults);
          },
        },
      ]
    );
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        style={[styles.container, { paddingTop: insets.top }]}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Settings</Text>
        </View>

        {/* Connection settings */}
        <SettingsSection title="Connection">
          <SettingsInput
            label="Backend URL"
            value={backendUrl}
            placeholder="http://192.168.1.10:8000"
            onChangeText={setBackendUrl}
            keyboardType="url"
          />
          <SettingsInput
            label="MQTT Broker URL"
            value={mqttUrl}
            placeholder="ws://192.168.1.10:9001"
            onChangeText={setMqttUrl}
            keyboardType="url"
          />

          {/* Test Connection button */}
          <TouchableOpacity
            style={[styles.testBtn, testing && styles.testBtnDisabled]}
            onPress={handleTest}
            disabled={testing}
          >
            {testing ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <>
                <Ionicons name="wifi" size={16} color="#FFFFFF" />
                <Text style={styles.testBtnText}>Test Connection</Text>
              </>
            )}
          </TouchableOpacity>

          {testResult && (
            <View
              style={[
                styles.testResult,
                {
                  backgroundColor: testResult.ok ? "#DCFCE7" : "#FEE2E2",
                  borderColor: testResult.ok ? "#22C55E" : "#EF4444",
                },
              ]}
            >
              <Ionicons
                name={testResult.ok ? "checkmark-circle" : "close-circle"}
                size={16}
                color={testResult.ok ? "#16A34A" : "#DC2626"}
              />
              <Text
                style={[
                  styles.testResultText,
                  { color: testResult.ok ? "#15803D" : "#B91C1C" },
                ]}
              >
                {testResult.message}
              </Text>
            </View>
          )}
        </SettingsSection>

        {/* Notifications */}
        <SettingsSection title="Notifications">
          <View style={styles.toggleRow}>
            <View style={styles.toggleInfo}>
              <Text style={styles.toggleLabel}>Push Notifications</Text>
              <Text style={styles.toggleSubLabel}>
                Receive HIGH severity alerts instantly
              </Text>
            </View>
            <Switch
              value={pushEnabled}
              onValueChange={setPushEnabled}
              trackColor={{ false: "#D1D5DB", true: "#93C5FD" }}
              thumbColor={pushEnabled ? "#2563EB" : "#9CA3AF"}
            />
          </View>
        </SettingsSection>

        {/* Save / Reset */}
        <SettingsSection title="Actions">
          <TouchableOpacity style={styles.saveBtn} onPress={handleSave}>
            <Ionicons name="save-outline" size={18} color="#FFFFFF" />
            <Text style={styles.saveBtnText}>
              {saved ? "Saved!" : "Save Settings"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.resetBtn} onPress={handleReset}>
            <Ionicons name="refresh-outline" size={18} color="#6B7280" />
            <Text style={styles.resetBtnText}>Reset to Defaults</Text>
          </TouchableOpacity>
        </SettingsSection>

        {/* App info */}
        <View style={styles.appInfo}>
          <Ionicons name="shield-checkmark" size={24} color="#2563EB" />
          <Text style={styles.appName}>Vantag</Text>
          <Text style={styles.appVersion}>Version {APP_VERSION}</Text>
          <Text style={styles.appCopy}>
            © 2024 Vantag Retail Intelligence
          </Text>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F9FAFB" },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: "#FFFFFF",
    borderBottomWidth: 1,
    borderBottomColor: "#E5E7EB",
  },
  headerTitle: { fontSize: 20, fontWeight: "700", color: "#111827" },
  section: {
    backgroundColor: "#FFFFFF",
    margin: 12,
    borderRadius: 12,
    padding: 16,
    elevation: 1,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 1 },
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    marginBottom: 14,
  },
  inputGroup: { marginBottom: 14 },
  inputLabel: { fontSize: 13, fontWeight: "600", color: "#374151", marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: "#D1D5DB",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: "#111827",
    backgroundColor: "#F9FAFB",
  },
  testBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#2563EB",
    borderRadius: 8,
    paddingVertical: 12,
    gap: 8,
    marginTop: 4,
  },
  testBtnDisabled: { opacity: 0.6 },
  testBtnText: { color: "#FFFFFF", fontWeight: "600", fontSize: 14 },
  testResult: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 10,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    gap: 8,
  },
  testResultText: { fontSize: 13, flex: 1 },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  toggleInfo: { flex: 1, marginRight: 12 },
  toggleLabel: { fontSize: 14, fontWeight: "600", color: "#111827" },
  toggleSubLabel: { fontSize: 12, color: "#6B7280", marginTop: 2 },
  saveBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#2563EB",
    borderRadius: 8,
    paddingVertical: 13,
    gap: 8,
    marginBottom: 10,
  },
  saveBtnText: { color: "#FFFFFF", fontWeight: "700", fontSize: 15 },
  resetBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F3F4F6",
    borderRadius: 8,
    paddingVertical: 13,
    gap: 8,
  },
  resetBtnText: { color: "#6B7280", fontWeight: "600", fontSize: 14 },
  appInfo: {
    alignItems: "center",
    paddingVertical: 24,
    gap: 4,
  },
  appName: { fontSize: 18, fontWeight: "700", color: "#111827", marginTop: 4 },
  appVersion: { fontSize: 13, color: "#6B7280" },
  appCopy: { fontSize: 11, color: "#9CA3AF" },
});
