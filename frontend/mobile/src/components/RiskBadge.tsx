/**
 * src/components/RiskBadge.tsx
 * ============================
 * Reusable risk severity badge component.
 *
 * Props:
 *  - score: number       (0–100)
 *  - severity: Severity  ('LOW' | 'MEDIUM' | 'HIGH')
 *  - compact?: boolean   (smaller pill variant, default false)
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Severity } from "../store/useMobileStore";

// ─── Colour mapping ───────────────────────────────────────────────────────────

const SEVERITY_STYLES: Record<
  Severity,
  { bg: string; text: string; border: string }
> = {
  LOW: { bg: "#DCFCE7", text: "#15803D", border: "#22C55E" },
  MEDIUM: { bg: "#FEF3C7", text: "#92400E", border: "#F59E0B" },
  HIGH: { bg: "#FEE2E2", text: "#991B1B", border: "#EF4444" },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface RiskBadgeProps {
  score: number;
  severity: Severity;
  compact?: boolean;
}

// ─── RiskBadge ────────────────────────────────────────────────────────────────

export default function RiskBadge({
  score,
  severity,
  compact = false,
}: RiskBadgeProps) {
  const { bg, text, border } = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.LOW;

  if (compact) {
    return (
      <View style={[styles.compact, { backgroundColor: bg, borderColor: border }]}>
        <Text style={[styles.compactText, { color: text }]}>
          {Math.round(score)}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.badge, { backgroundColor: bg, borderColor: border }]}>
      <Text style={[styles.scoreText, { color: text }]}>
        {Math.round(score)}
      </Text>
      <Text style={[styles.severityText, { color: text }]}>{severity}</Text>
    </View>
  );
}

// ─── Large circular variant ───────────────────────────────────────────────────

interface RiskBadgeLargeProps {
  score: number;
  severity: Severity;
  size?: number;
}

export function RiskBadgeLarge({
  score,
  severity,
  size = 80,
}: RiskBadgeLargeProps) {
  const { bg, text, border } = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.LOW;

  return (
    <View
      style={[
        styles.circle,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: bg,
          borderColor: border,
        },
      ]}
    >
      <Text style={[styles.circleScore, { color: text, fontSize: size * 0.32 }]}>
        {Math.round(score)}
      </Text>
      <Text
        style={[
          styles.circleLabel,
          { color: text, fontSize: size * 0.14 },
        ]}
      >
        {severity}
      </Text>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 20,
    borderWidth: 1,
    gap: 5,
  },
  scoreText: {
    fontSize: 14,
    fontWeight: "800",
  },
  severityText: {
    fontSize: 11,
    fontWeight: "700",
  },
  compact: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  compactText: {
    fontSize: 13,
    fontWeight: "800",
  },
  circle: {
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  circleScore: {
    fontWeight: "800",
    lineHeight: undefined,
  },
  circleLabel: {
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
});
