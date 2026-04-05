/**
 * src/screens/StoreDetailScreen.tsx
 * ==================================
 * Detailed view for a single retail store.
 *
 * Sections:
 *  - Large risk score display
 *  - Camera thumbnails grid (snapshot images)
 *  - Door control section with OneTapLockButton
 *  - Recent events list (last 20)
 *  - Queue status lane cards
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  FlatList,
  RefreshControl,
} from "react-native";
import { useRoute, RouteProp } from "@react-navigation/native";
import axios from "axios";

import { useMobileStore, Camera, VantagEvent, QueueStatus, Severity } from "../store/useMobileStore";
import { HomeStackParamList } from "../../App";
import RiskBadge from "../components/RiskBadge";
import OneTapLockButton from "../components/OneTapLockButton";

type DetailRoute = RouteProp<HomeStackParamList, "StoreDetail">;

// ─── Queue lane card ──────────────────────────────────────────────────────────

function QueueLaneCard({ lane }: { lane: QueueStatus }) {
  const bg =
    lane.status === "critical"
      ? "#FEE2E2"
      : lane.status === "busy"
      ? "#FEF3C7"
      : "#DCFCE7";
  const statusColor =
    lane.status === "critical"
      ? "#EF4444"
      : lane.status === "busy"
      ? "#F59E0B"
      : "#22C55E";

  return (
    <View style={[styles.laneCard, { backgroundColor: bg }]}>
      <Text style={styles.laneId}>{lane.lane_id}</Text>
      <View style={styles.laneStats}>
        <Text style={styles.laneDepth}>{lane.queue_depth}</Text>
        <Text style={styles.laneLabel}>in queue</Text>
      </View>
      <Text style={[styles.laneStatus, { color: statusColor }]}>
        {lane.status.toUpperCase()}
      </Text>
      <Text style={styles.laneWait}>
        ~{Math.round(lane.avg_wait_seconds)}s wait
      </Text>
    </View>
  );
}

// ─── Event row ────────────────────────────────────────────────────────────────

function eventSeverityColor(sev: Severity): string {
  return sev === "HIGH" ? "#EF4444" : sev === "MEDIUM" ? "#F59E0B" : "#22C55E";
}

function EventRow({ event }: { event: VantagEvent }) {
  return (
    <View style={styles.eventRow}>
      <View
        style={[
          styles.severityDot,
          { backgroundColor: eventSeverityColor(event.severity) },
        ]}
      />
      <View style={styles.eventBody}>
        <Text style={styles.eventDesc} numberOfLines={2}>
          {event.description}
        </Text>
        <Text style={styles.eventTime}>
          {new Date(event.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </Text>
      </View>
      <View
        style={[
          styles.severityBadge,
          { backgroundColor: eventSeverityColor(event.severity) + "22" },
        ]}
      >
        <Text
          style={[
            styles.severityBadgeText,
            { color: eventSeverityColor(event.severity) },
          ]}
        >
          {event.severity}
        </Text>
      </View>
    </View>
  );
}

// ─── StoreDetailScreen ────────────────────────────────────────────────────────

export default function StoreDetailScreen() {
  const route = useRoute<DetailRoute>();
  const { storeId } = route.params;

  const backendUrl = useMobileStore((s) => s.settings.backendUrl);
  const riskScore = useMobileStore((s) => s.riskScores[storeId]);
  const allEvents = useMobileStore((s) => s.recentEvents);
  const allCameras = useMobileStore((s) => s.cameras);
  const queueStatuses = useMobileStore((s) => s.queueStatuses);
  const setCameras = useMobileStore((s) => s.setCameras);
  const setQueueStatuses = useMobileStore((s) => s.setQueueStatuses);

  const storeCameras = allCameras.filter((c) => c.store_id === storeId);
  const storeEvents = allEvents
    .filter((e) => e.store_id === storeId)
    .slice(0, 20);
  const storeLanes = queueStatuses.filter((q) => q.store_id === storeId);

  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [camRes, queueRes] = await Promise.all([
        axios.get<Camera[]>(`${backendUrl}/api/cameras?store_id=${storeId}`, {
          timeout: 8000,
        }),
        axios.get<{ lanes: QueueStatus[] }>(
          `${backendUrl}/api/stores/${storeId}/queue`,
          { timeout: 8000 }
        ),
      ]);
      const existingCams = useMobileStore.getState().cameras;
      const otherCams = existingCams.filter((c) => c.store_id !== storeId);
      setCameras([...otherCams, ...camRes.data]);
      setQueueStatuses(queueRes.data.lanes ?? []);
    } catch {
      // Non-fatal — display cached data
    } finally {
      setRefreshing(false);
    }
  }, [backendUrl, storeId]);

  useEffect(() => {
    fetchData();
  }, [storeId]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchData();
  }, [fetchData]);

  // Current score display value
  const scoreValue = riskScore?.score ?? 0;
  const scoreSeverity: Severity = riskScore?.severity ?? "LOW";

  const riskBg =
    scoreSeverity === "HIGH"
      ? "#EF4444"
      : scoreSeverity === "MEDIUM"
      ? "#F59E0B"
      : "#22C55E";

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2563EB" />
      }
    >
      {/* ── Risk Score Hero ─────────────────────────────────────────── */}
      <View style={[styles.riskHero, { backgroundColor: riskBg }]}>
        <Text style={styles.riskScoreValue}>{Math.round(scoreValue)}</Text>
        <Text style={styles.riskScoreLabel}>Risk Score</Text>
        <View style={styles.riskSeverityPill}>
          <Text style={styles.riskSeverityText}>{scoreSeverity}</Text>
        </View>
      </View>

      {/* ── Camera Thumbnails ───────────────────────────────────────── */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Cameras</Text>
        {storeCameras.length === 0 ? (
          <Text style={styles.emptyText}>No cameras for this store.</Text>
        ) : (
          <View style={styles.cameraGrid}>
            {storeCameras.map((cam) => (
              <View key={cam.camera_id} style={styles.cameraThumb}>
                <Image
                  source={{
                    uri: `${backendUrl}/api/cameras/${cam.camera_id}/snapshot`,
                  }}
                  style={styles.cameraImage}
                  resizeMode="cover"
                />
                <View
                  style={[
                    styles.cameraStatusDot,
                    {
                      backgroundColor:
                        cam.status === "online" ? "#22C55E" : "#EF4444",
                    },
                  ]}
                />
                <Text style={styles.cameraName} numberOfLines={1}>
                  {cam.name}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* ── Door Control ────────────────────────────────────────────── */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Door Control</Text>
        <View style={styles.doorRow}>
          <OneTapLockButton storeId={storeId} doorId="main" />
          <OneTapLockButton storeId={storeId} doorId="rear" />
        </View>
      </View>

      {/* ── Queue Status ─────────────────────────────────────────────── */}
      {storeLanes.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Queue Lanes</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={styles.laneRow}>
              {storeLanes.map((lane) => (
                <QueueLaneCard key={lane.lane_id} lane={lane} />
              ))}
            </View>
          </ScrollView>
        </View>
      )}

      {/* ── Recent Events ────────────────────────────────────────────── */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Recent Events</Text>
        {storeEvents.length === 0 ? (
          <Text style={styles.emptyText}>No recent events.</Text>
        ) : (
          storeEvents.map((ev) => <EventRow key={ev.id} event={ev} />)
        )}
      </View>

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F9FAFB" },
  riskHero: {
    alignItems: "center",
    paddingVertical: 32,
    paddingHorizontal: 16,
  },
  riskScoreValue: {
    fontSize: 72,
    fontWeight: "800",
    color: "#FFFFFF",
    lineHeight: 80,
  },
  riskScoreLabel: {
    fontSize: 16,
    color: "#FFFFFF",
    opacity: 0.85,
    marginTop: 4,
  },
  riskSeverityPill: {
    marginTop: 12,
    backgroundColor: "rgba(0,0,0,0.2)",
    borderRadius: 20,
    paddingHorizontal: 20,
    paddingVertical: 6,
  },
  riskSeverityText: { color: "#FFFFFF", fontWeight: "700", fontSize: 14 },
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
    fontSize: 16,
    fontWeight: "700",
    color: "#111827",
    marginBottom: 12,
  },
  cameraGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  cameraThumb: { width: "47%", borderRadius: 8, overflow: "hidden" },
  cameraImage: { width: "100%", height: 90, backgroundColor: "#1F2937" },
  cameraStatusDot: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: "#FFFFFF",
  },
  cameraName: {
    fontSize: 11,
    color: "#374151",
    padding: 4,
    backgroundColor: "#F3F4F6",
  },
  doorRow: { flexDirection: "row", gap: 12 },
  laneRow: { flexDirection: "row", gap: 10, paddingBottom: 4 },
  laneCard: {
    borderRadius: 10,
    padding: 14,
    alignItems: "center",
    minWidth: 110,
  },
  laneId: { fontSize: 12, color: "#6B7280", marginBottom: 6 },
  laneStats: { alignItems: "center" },
  laneDepth: { fontSize: 32, fontWeight: "800", color: "#111827" },
  laneLabel: { fontSize: 11, color: "#6B7280" },
  laneStatus: { fontSize: 12, fontWeight: "700", marginTop: 4 },
  laneWait: { fontSize: 11, color: "#6B7280", marginTop: 2 },
  eventRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#F3F4F6",
  },
  severityDot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  eventBody: { flex: 1, marginRight: 8 },
  eventDesc: { fontSize: 13, color: "#374151" },
  eventTime: { fontSize: 11, color: "#9CA3AF", marginTop: 2 },
  severityBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  severityBadgeText: { fontSize: 11, fontWeight: "700" },
  emptyText: { color: "#9CA3AF", fontSize: 13, textAlign: "center", padding: 8 },
});
