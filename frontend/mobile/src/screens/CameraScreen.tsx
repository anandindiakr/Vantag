/**
 * src/screens/CameraScreen.tsx
 * ============================
 * Camera grid and live stream viewer.
 *
 * Features:
 *  - Grid of camera cards with health status indicators
 *  - Tap a camera → fullscreen modal with WebView MJPEG stream
 *  - Camera name and location overlay on cards
 */

import React, { useState, useCallback, useEffect } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Modal,
  SafeAreaView,
  StatusBar,
  ActivityIndicator,
  ListRenderItem,
  Dimensions,
  Image,
} from "react-native";
import { WebView } from "react-native-webview";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import axios from "axios";

import { useMobileStore, Camera } from "../store/useMobileStore";

const { width: SCREEN_WIDTH } = Dimensions.get("window");
const CARD_WIDTH = (SCREEN_WIDTH - 36) / 2;

// ─── Status indicator ─────────────────────────────────────────────────────────

function StatusIndicator({ status }: { status: Camera["status"] }) {
  const color =
    status === "online" ? "#22C55E" : status === "degraded" ? "#F59E0B" : "#EF4444";
  const label =
    status === "online" ? "ONLINE" : status === "degraded" ? "DEGRADED" : "OFFLINE";
  return (
    <View style={[styles.statusPill, { backgroundColor: color + "33" }]}>
      <View style={[styles.statusDot, { backgroundColor: color }]} />
      <Text style={[styles.statusText, { color }]}>{label}</Text>
    </View>
  );
}

// ─── Camera Card ──────────────────────────────────────────────────────────────

function CameraCard({
  camera,
  backendUrl,
  onPress,
}: {
  camera: Camera;
  backendUrl: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      {/* Thumbnail */}
      <Image
        source={{ uri: `${backendUrl}/api/cameras/${camera.camera_id}/snapshot` }}
        style={styles.thumbnail}
        resizeMode="cover"
      />

      {/* Status pill overlay */}
      <View style={styles.statusOverlay}>
        <StatusIndicator status={camera.status} />
      </View>

      {/* Play icon */}
      {camera.status === "online" && (
        <View style={styles.playIcon}>
          <Ionicons name="play-circle" size={32} color="rgba(255,255,255,0.85)" />
        </View>
      )}

      {/* Camera info */}
      <View style={styles.cardInfo}>
        <Text style={styles.cameraName} numberOfLines={1}>
          {camera.name}
        </Text>
        <Text style={styles.cameraLocation} numberOfLines={1}>
          {camera.location}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

// ─── Stream Modal ─────────────────────────────────────────────────────────────

function StreamModal({
  camera,
  backendUrl,
  visible,
  onClose,
}: {
  camera: Camera | null;
  backendUrl: string;
  visible: boolean;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (visible) setLoading(true);
  }, [visible, camera?.camera_id]);

  if (!camera) return null;

  // Stream URL — try MJPEG endpoint, fallback to RTSP proxy page
  const streamUrl = `${backendUrl}/api/cameras/${camera.camera_id}/stream`;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.modal}>
        <StatusBar barStyle="light-content" backgroundColor="#000000" />

        {/* Header */}
        <View style={styles.modalHeader}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <View style={styles.modalTitleBlock}>
            <Text style={styles.modalTitle} numberOfLines={1}>
              {camera.name}
            </Text>
            <Text style={styles.modalSubtitle} numberOfLines={1}>
              {camera.location}
            </Text>
          </View>
          <StatusIndicator status={camera.status} />
        </View>

        {/* Stream */}
        <View style={styles.streamContainer}>
          {loading && (
            <View style={styles.streamLoader}>
              <ActivityIndicator size="large" color="#FFFFFF" />
              <Text style={styles.streamLoaderText}>Connecting to stream…</Text>
            </View>
          )}
          <WebView
            source={{ uri: streamUrl }}
            style={styles.webview}
            onLoadStart={() => setLoading(true)}
            onLoad={() => setLoading(false)}
            onError={() => setLoading(false)}
            mediaPlaybackRequiresUserAction={false}
            allowsInlineMediaPlayback
            javaScriptEnabled
          />
        </View>

        {/* Camera metadata footer */}
        <View style={styles.streamFooter}>
          <Text style={styles.footerText}>
            {camera.resolution_width}×{camera.resolution_height} · {camera.fps_target} fps
          </Text>
          <Text style={styles.footerText}>{camera.camera_id}</Text>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

// ─── CameraScreen ─────────────────────────────────────────────────────────────

export default function CameraScreen() {
  const insets = useSafeAreaInsets();
  const cameras = useMobileStore((s) => s.cameras);
  const setCameras = useMobileStore((s) => s.setCameras);
  const backendUrl = useMobileStore((s) => s.settings.backendUrl);

  const [selected, setSelected] = useState<Camera | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchCameras = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get<Camera[]>(`${backendUrl}/api/cameras`, {
        timeout: 8000,
      });
      setCameras(res.data);
    } catch {
      // Silent — use cached data
    } finally {
      setLoading(false);
    }
  }, [backendUrl]);

  useEffect(() => {
    fetchCameras();
  }, [backendUrl]);

  const openCamera = useCallback((cam: Camera) => {
    setSelected(cam);
    setModalVisible(true);
  }, []);

  const renderItem: ListRenderItem<Camera> = useCallback(
    ({ item }) => (
      <CameraCard
        camera={item}
        backendUrl={backendUrl}
        onPress={() => openCamera(item)}
      />
    ),
    [backendUrl, openCamera]
  );

  const keyExtractor = useCallback((item: Camera) => item.camera_id, []);

  const online = cameras.filter((c) => c.status === "online").length;
  const total = cameras.length;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Cameras</Text>
        <Text style={styles.headerSub}>
          {online}/{total} online
        </Text>
      </View>

      {loading && cameras.length === 0 ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#2563EB" />
          <Text style={styles.loadingText}>Loading cameras…</Text>
        </View>
      ) : (
        <FlatList
          data={cameras}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          numColumns={2}
          columnWrapperStyle={styles.columnWrapper}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Ionicons name="videocam-off-outline" size={48} color="#D1D5DB" />
              <Text style={styles.emptyText}>No cameras configured.</Text>
            </View>
          }
        />
      )}

      <StreamModal
        camera={selected}
        backendUrl={backendUrl}
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
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
  headerSub: { fontSize: 13, color: "#6B7280" },
  listContent: { padding: 12 },
  columnWrapper: { gap: 12, marginBottom: 12 },
  card: {
    width: CARD_WIDTH,
    backgroundColor: "#1F2937",
    borderRadius: 12,
    overflow: "hidden",
  },
  thumbnail: { width: "100%", height: 110 },
  statusOverlay: {
    position: "absolute",
    top: 8,
    left: 8,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 10,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3, marginRight: 4 },
  statusText: { fontSize: 10, fontWeight: "700" },
  playIcon: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  cardInfo: { padding: 8 },
  cameraName: { fontSize: 13, fontWeight: "600", color: "#FFFFFF" },
  cameraLocation: { fontSize: 11, color: "#9CA3AF", marginTop: 2 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32 },
  loadingText: { color: "#6B7280", marginTop: 12 },
  emptyText: { color: "#9CA3AF", marginTop: 12 },
  modal: { flex: 1, backgroundColor: "#000000" },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: "#111827",
  },
  closeBtn: { padding: 4, marginRight: 12 },
  modalTitleBlock: { flex: 1, marginRight: 8 },
  modalTitle: { fontSize: 16, fontWeight: "700", color: "#FFFFFF" },
  modalSubtitle: { fontSize: 12, color: "#9CA3AF" },
  streamContainer: { flex: 1, backgroundColor: "#000000" },
  streamLoader: {
    position: "absolute",
    top: 0, left: 0, right: 0, bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10,
  },
  streamLoaderText: { color: "#FFFFFF", marginTop: 12 },
  webview: { flex: 1 },
  streamFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: "#111827",
  },
  footerText: { fontSize: 12, color: "#6B7280" },
});
