/**
 * src/screens/AlertsScreen.tsx
 * ============================
 * Real-time alert feed screen.
 *
 * Features:
 *  - FlatList of events (newest first)
 *  - Filter buttons: ALL / HIGH / MEDIUM / LOW
 *  - Event type icon, description, timestamp, severity badge
 *  - Mark-all-read action
 */

import React, { useCallback, useMemo, useState } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ListRenderItem,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { useMobileStore, VantagEvent, Severity } from "../store/useMobileStore";

// ─── Type constants ───────────────────────────────────────────────────────────

type FilterLevel = "ALL" | Severity;

const FILTER_OPTIONS: FilterLevel[] = ["ALL", "HIGH", "MEDIUM", "LOW"];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function severityColor(sev: Severity): string {
  return sev === "HIGH" ? "#EF4444" : sev === "MEDIUM" ? "#F59E0B" : "#22C55E";
}

function eventTypeIcon(type: string): keyof typeof Ionicons.glyphMap {
  const map: Record<string, keyof typeof Ionicons.glyphMap> = {
    sweeping: "hand-left",
    dwell: "time",
    empty_shelf: "cube-outline",
    watchlist_match: "person-circle",
    queue: "people",
    accident: "warning",
    staff_alert: "person-circle-outline",
    tamper: "eye-off",
    pos_anomaly: "card",
  };
  return map[type] ?? "alert-circle";
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);

  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return d.toLocaleDateString();
}

// ─── Event Row ────────────────────────────────────────────────────────────────

function AlertRow({
  event,
  onPress,
}: {
  event: VantagEvent;
  onPress: () => void;
}) {
  const color = severityColor(event.severity);
  const icon = eventTypeIcon(event.type);

  return (
    <TouchableOpacity
      style={[styles.row, !event.read && styles.rowUnread]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      {/* Unread indicator */}
      {!event.read && <View style={styles.unreadDot} />}

      {/* Icon */}
      <View style={[styles.iconBox, { backgroundColor: color + "22" }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>

      {/* Content */}
      <View style={styles.rowContent}>
        <View style={styles.rowHeader}>
          <Text style={styles.rowType}>
            {event.type.replace(/_/g, " ").toUpperCase()}
          </Text>
          <Text style={styles.rowTime}>{formatTimestamp(event.timestamp)}</Text>
        </View>
        <Text style={styles.rowDesc} numberOfLines={2}>
          {event.description}
        </Text>
        <Text style={styles.rowCamera} numberOfLines={1}>
          {event.camera_id} · {event.store_id}
        </Text>
      </View>

      {/* Severity badge */}
      <View style={[styles.badge, { backgroundColor: color }]}>
        <Text style={styles.badgeText}>{event.severity}</Text>
      </View>
    </TouchableOpacity>
  );
}

// ─── Filter Button ────────────────────────────────────────────────────────────

function FilterButton({
  label,
  active,
  count,
  onPress,
}: {
  label: FilterLevel;
  active: boolean;
  count: number;
  onPress: () => void;
}) {
  const bg = active ? "#2563EB" : "#F3F4F6";
  const textColor = active ? "#FFFFFF" : "#374151";

  return (
    <TouchableOpacity
      style={[styles.filterBtn, { backgroundColor: bg }]}
      onPress={onPress}
    >
      <Text style={[styles.filterText, { color: textColor }]}>
        {label}
        {count > 0 ? ` (${count})` : ""}
      </Text>
    </TouchableOpacity>
  );
}

// ─── AlertsScreen ─────────────────────────────────────────────────────────────

export default function AlertsScreen() {
  const insets = useSafeAreaInsets();
  const events = useMobileStore((s) => s.recentEvents);
  const markEventRead = useMobileStore((s) => s.markEventRead);
  const markAllRead = useMobileStore((s) => s.markAllRead);

  const [filter, setFilter] = useState<FilterLevel>("ALL");

  // Counts per filter level
  const counts = useMemo(() => {
    return {
      ALL: events.length,
      HIGH: events.filter((e) => e.severity === "HIGH").length,
      MEDIUM: events.filter((e) => e.severity === "MEDIUM").length,
      LOW: events.filter((e) => e.severity === "LOW").length,
    };
  }, [events]);

  const filtered = useMemo(
    () =>
      filter === "ALL" ? events : events.filter((e) => e.severity === filter),
    [events, filter]
  );

  const unreadCount = useMemo(
    () => events.filter((e) => !e.read).length,
    [events]
  );

  const renderItem: ListRenderItem<VantagEvent> = useCallback(
    ({ item }) => (
      <AlertRow event={item} onPress={() => markEventRead(item.id)} />
    ),
    [markEventRead]
  );

  const keyExtractor = useCallback((item: VantagEvent) => item.id, []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Alerts</Text>
        {unreadCount > 0 && (
          <TouchableOpacity onPress={markAllRead} style={styles.readAllBtn}>
            <Text style={styles.readAllText}>Mark all read</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Filter row */}
      <View style={styles.filterRow}>
        {FILTER_OPTIONS.map((opt) => (
          <FilterButton
            key={opt}
            label={opt}
            active={filter === opt}
            count={opt === "ALL" ? 0 : counts[opt]}
            onPress={() => setFilter(opt)}
          />
        ))}
      </View>

      {/* Event list */}
      <FlatList
        data={filtered}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="checkmark-circle-outline" size={48} color="#D1D5DB" />
            <Text style={styles.emptyText}>No alerts</Text>
          </View>
        }
      />
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F9FAFB" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: "#FFFFFF",
    borderBottomWidth: 1,
    borderBottomColor: "#E5E7EB",
  },
  headerTitle: { fontSize: 20, fontWeight: "700", color: "#111827" },
  readAllBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: "#EFF6FF",
    borderRadius: 8,
  },
  readAllText: { color: "#2563EB", fontSize: 13, fontWeight: "600" },
  filterRow: {
    flexDirection: "row",
    padding: 12,
    gap: 8,
    backgroundColor: "#FFFFFF",
    borderBottomWidth: 1,
    borderBottomColor: "#F3F4F6",
  },
  filterBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  filterText: { fontSize: 13, fontWeight: "600" },
  listContent: { padding: 12, gap: 8 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    padding: 12,
    elevation: 1,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 1 },
    position: "relative",
  },
  rowUnread: {
    borderLeftWidth: 3,
    borderLeftColor: "#2563EB",
  },
  unreadDot: {
    position: "absolute",
    top: 8,
    left: 8,
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#2563EB",
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  rowContent: { flex: 1, marginRight: 8 },
  rowHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  rowType: { fontSize: 11, fontWeight: "700", color: "#6B7280" },
  rowTime: { fontSize: 11, color: "#9CA3AF" },
  rowDesc: { fontSize: 13, color: "#111827", marginBottom: 2 },
  rowCamera: { fontSize: 11, color: "#9CA3AF" },
  badge: {
    borderRadius: 6,
    paddingHorizontal: 7,
    paddingVertical: 3,
    alignSelf: "center",
  },
  badgeText: { color: "#FFFFFF", fontSize: 10, fontWeight: "700" },
  empty: { alignItems: "center", justifyContent: "center", padding: 48 },
  emptyText: { color: "#9CA3AF", fontSize: 15, marginTop: 12 },
});
