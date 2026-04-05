/**
 * src/components/OneTapLockButton.tsx
 * =====================================
 * One-tap door lock / unlock button component.
 *
 * Features:
 *  - TouchableOpacity with padlock icon
 *  - Red background = locked, green = unlocked
 *  - ActivityIndicator while command in flight
 *  - Publishes door command via backend REST API (which in turn publishes MQTT)
 *  - Shows Toast on success / failure
 */

import React, { useState } from "react";
import {
  TouchableOpacity,
  View,
  Text,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Toast from "react-native-toast-message";
import axios from "axios";

import { useMobileStore, DoorState } from "../store/useMobileStore";

// ─── Props ────────────────────────────────────────────────────────────────────

interface OneTapLockButtonProps {
  storeId: string;
  doorId: string;
  issuedBy?: string;
}

// ─── OneTapLockButton ─────────────────────────────────────────────────────────

export default function OneTapLockButton({
  storeId,
  doorId,
  issuedBy = "mobile-app",
}: OneTapLockButtonProps) {
  const backendUrl = useMobileStore((s) => s.settings.backendUrl);
  const doorStates = useMobileStore((s) => s.doorStates);
  const setDoorState = useMobileStore((s) => s.setDoorState);

  const key = `${storeId}/${doorId}`;
  const doorEntry = doorStates[key];
  const currentState: DoorState["state"] = doorEntry?.state ?? "unknown";
  const isLocked = currentState === "locked";

  const [loading, setLoading] = useState(false);

  const handlePress = async () => {
    if (loading) return;

    const action = isLocked ? "unlock" : "lock";
    const endpoint = `${backendUrl}/api/doors/${storeId}/${doorId}/${action}`;

    setLoading(true);

    try {
      const res = await axios.post<{
        state: DoorState["state"];
        door_id: string;
        store_id: string;
        last_command_at: string | null;
      }>(
        endpoint,
        { action, issued_by: issuedBy },
        { timeout: 8000 }
      );

      setDoorState({
        door_id: res.data.door_id,
        store_id: res.data.store_id,
        state: res.data.state,
        last_command_at: res.data.last_command_at,
      });

      Toast.show({
        type: "success",
        text1: `Door ${action === "lock" ? "Locked" : "Unlocked"}`,
        text2: `${doorId} · ${storeId}`,
        visibilityTime: 2500,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Command failed";
      Toast.show({
        type: "error",
        text1: "Command Failed",
        text2: msg,
        visibilityTime: 3500,
      });
    } finally {
      setLoading(false);
    }
  };

  // ── Appearance ────────────────────────────────────────────────────────────

  const bgColor =
    currentState === "locked"
      ? "#EF4444"
      : currentState === "unlocked"
      ? "#22C55E"
      : "#6B7280";

  const iconName: keyof typeof Ionicons.glyphMap =
    currentState === "locked" ? "lock-closed" : "lock-open";

  const label =
    currentState === "locked"
      ? "Locked"
      : currentState === "unlocked"
      ? "Unlocked"
      : "Unknown";

  const actionLabel =
    currentState === "locked" ? "Tap to Unlock" : "Tap to Lock";

  return (
    <TouchableOpacity
      style={[styles.button, { backgroundColor: bgColor }]}
      onPress={handlePress}
      activeOpacity={0.8}
      disabled={loading}
    >
      {loading ? (
        <ActivityIndicator size="small" color="#FFFFFF" />
      ) : (
        <Ionicons name={iconName} size={22} color="#FFFFFF" />
      )}
      <View style={styles.textBlock}>
        <Text style={styles.doorId} numberOfLines={1}>
          {doorId.toUpperCase()}
        </Text>
        <Text style={styles.stateLabel}>{label}</Text>
        <Text style={styles.actionHint}>{loading ? "Sending…" : actionLabel}</Text>
      </View>
    </TouchableOpacity>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  button: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
    minWidth: 120,
    elevation: 2,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
  },
  textBlock: { flex: 1 },
  doorId: {
    fontSize: 11,
    fontWeight: "700",
    color: "rgba(255,255,255,0.75)",
    textTransform: "uppercase",
  },
  stateLabel: {
    fontSize: 15,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  actionHint: {
    fontSize: 11,
    color: "rgba(255,255,255,0.75)",
    marginTop: 2,
  },
});
