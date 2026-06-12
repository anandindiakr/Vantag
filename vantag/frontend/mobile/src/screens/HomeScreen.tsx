/**
 * src/screens/HomeScreen.tsx
 * ==========================
 * Store list screen — the main landing screen of the Vantag mobile app.
 *
 * Features:
 *  - FlatList of store cards with risk score (color-coded red/amber/green)
 *  - Pull-to-refresh to reload store data
 *  - Tap a card → navigate to StoreDetailScreen
 *  - Connection status badge in header
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  ListRenderItem,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import axios from "axios";

import { useMobileStore, Store, Severity } from "../store/useMobileStore";
import { HomeStackParamList } from "../../App";
import RiskBadge from "../components/RiskBadge";

type HomeNav = NativeStackNavigationProp<HomeStackParamList, "StoreList">;

// ─── Risk colour mapping ──────────────────────────────────────────────────────

function severityBackground(severity: Severity): string {
  switch (severity) {
    case "HIGH":
      return "#FEE2E2"; // red-100
    case "MEDIUM":
      return "#FEF3C7"; // amber-100
    default:
      return "#DCFCE7"; // green-100
  }
}

function severityBorder(severity: Severity): string {
  switch (severity) {
    case "HIGH":
      return "#EF4444";
    case "MEDIUM":
      return "#F59E0B";
    default:
      return "#22C55E";
  }
}

// ─── Store Card ───────────────────────────────────────────────────────────────

interface StoreCardProps {
  store: Store;
  onPress: () => void;
}

function StoreCard({ store, onPress }: StoreCardProps) {
  const bg = severityBackground(store.risk_severity);
  const border = severityBorder(store.risk_severity);

  return (
    <TouchableOpacity
      style={[styles.card, { backgroundColor: bg, borderLeftColor: border }]}
      onPress={onPress}
      activeOpacity={0.75}
    >
      <View style={styles.cardHeader}>
        <Text style={styles.storeName} numberOfLines={1}>
          {store.name}
        </Text>
        <RiskBadge score={store.risk_score} severity={store.risk_severity} />
      </View>
      <Text style={styles.location} numberOfLines={1}>
        {store.location}
      </Text>
      <View style={styles.cardFooter}>
        <Text style={styles.cameraInfo}>
          {store.active_cameras}/{store.camera_count} cameras online
        </Text>
        {store.last_event_at && (
          <Text style={styles.lastEvent}>
            Last event:{" "}
            {new Date(store.last_event_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

// ─── Connection Badge ─────────────────────────────────────────────────────────

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: connected ? "#22C55E" : "#EF4444" },
      ]}
    >
      <Text style={styles.badgeText}>{connected ? "LIVE" : "OFFLINE"}</Text>
    </View>
  );
}

// ─── HomeScreen ───────────────────────────────────────────────────────────────

export default function HomeScreen() {
  const navigation = useNavigation<HomeNav>();
  const insets = useSafeAreaInsets();

  const stores = useMobileStore((s) => s.stores);
  const setStores = useMobileStore((s) => s.setStores);
  const wsConnected = useMobileStore((s) => s.wsConnected);
  const backendUrl = useMobileStore((s) => s.settings.backendUrl);

  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchStores = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setFetchError(null);
      try {
        const res = await axios.get<Store[]>(`${backendUrl}/api/stores`, {
          timeout: 10_000,
        });
        setStores(res.data);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Failed to load stores";
        setFetchError(msg);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [backendUrl]
  );

  useEffect(() => {
    fetchStores();
  }, [backendUrl]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchStores(true);
  }, [fetchStores]);

  const renderItem: ListRenderItem<Store> = useCallback(
    ({ item }) => (
      <StoreCard
        store={item}
        onPress={() =>
          navigation.navigate("StoreDetail", {
            storeId: item.store_id,
            storeName: item.name,
          })
        }
      />
    ),
    [navigation]
  );

  const keyExtractor = useCallback((item: Store) => item.store_id, []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header bar */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Stores</Text>
        <ConnectionBadge connected={wsConnected} />
      </View>

      {loading && stores.length === 0 ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#2563EB" />
          <Text style={styles.loadingText}>Loading stores…</Text>
        </View>
      ) : fetchError && stores.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{fetchError}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => fetchStores()}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={stores}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#2563EB"
            />
          }
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.emptyText}>No stores configured.</Text>
            </View>
          }
        />
      )}
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
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeText: { color: "#FFFFFF", fontSize: 11, fontWeight: "700" },
  list: { padding: 12, gap: 12 },
  card: {
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
    elevation: 2,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  storeName: {
    fontSize: 16,
    fontWeight: "700",
    color: "#111827",
    flex: 1,
    marginRight: 8,
  },
  location: { fontSize: 13, color: "#6B7280", marginBottom: 10 },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  cameraInfo: { fontSize: 12, color: "#6B7280" },
  lastEvent: { fontSize: 12, color: "#9CA3AF" },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  loadingText: { marginTop: 12, color: "#6B7280" },
  errorText: { color: "#DC2626", textAlign: "center", marginBottom: 12 },
  retryBtn: {
    backgroundColor: "#2563EB",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: { color: "#FFFFFF", fontWeight: "600" },
  emptyText: { color: "#9CA3AF", fontSize: 15 },
});
