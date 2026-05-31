import React from 'react';
import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/ThemeProvider';
import { FLAVOR_DIMS, flavor, flavorInk, radius, space, type FlavorDim } from '../theme/tokens';
import { Text } from '../ui/Text';

interface Props {
  /** dim -> 0..1 (the backend `flavor` map). */
  scores: Record<string, number>;
  variant?: 'spectrum' | 'lollipop';
  height?: number; // spectrum bar height
}

/**
 * The canonical flavor fingerprint. `spectrum` = a single pill bar whose segments are the 10
 * dims (width ∝ score, colored by the flavor `base`) — used on cards/feed. `lollipop` = a
 * labeled per-dim list used on the dish-detail screen. No radar, ever.
 */
export function FlavorFingerprint({ scores, variant = 'spectrum', height = 24 }: Props) {
  if (variant === 'lollipop') return <Lollipop scores={scores} />;
  return <Spectrum scores={scores} height={height} />;
}

function Spectrum({ scores, height }: { scores: Record<string, number>; height: number }) {
  const { c } = useTheme();
  const total = FLAVOR_DIMS.reduce((sum, d) => sum + Math.max(0, scores[d] ?? 0), 0);
  return (
    <View
      style={[styles.spectrum, { height, borderRadius: radius.pill, backgroundColor: c.hairline }]}
      accessibilityLabel="Flavor spectrum"
    >
      {total > 0 &&
        FLAVOR_DIMS.map((dim) => {
          const value = Math.max(0, scores[dim] ?? 0);
          if (value <= 0) return null;
          return <View key={dim} style={{ flex: value, backgroundColor: flavor[dim].base }} />;
        })}
    </View>
  );
}

function Lollipop({ scores }: { scores: Record<string, number> }) {
  const { scheme } = useTheme();
  return (
    <View style={{ gap: space.sm }}>
      {FLAVOR_DIMS.map((dim) => (
        <LollipopRow key={dim} dim={dim} value={Math.max(0, Math.min(1, scores[dim] ?? 0))} scheme={scheme} />
      ))}
    </View>
  );
}

function LollipopRow({ dim, value, scheme }: { dim: FlavorDim; value: number; scheme: 'light' | 'dark' }) {
  const { c } = useTheme();
  return (
    <View style={styles.row}>
      <Text variant="label" color={flavorInk(dim, scheme)} style={styles.rowLabel}>
        {dim}
      </Text>
      <View style={[styles.track, { backgroundColor: c.hairline }]}>
        <View style={[styles.stick, { width: `${value * 100}%`, backgroundColor: flavor[dim].base }]} />
        <View
          style={[styles.dot, { left: `${value * 100}%`, backgroundColor: flavor[dim].base }]}
        />
      </View>
      <Text variant="caption" tone="muted" tabular style={styles.rowValue}>
        {value.toFixed(2)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  spectrum: { flexDirection: 'row', width: '100%', overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowLabel: { width: 78, textTransform: 'capitalize' },
  track: { flex: 1, height: 4, borderRadius: radius.pill, justifyContent: 'center' },
  stick: { height: 4, borderRadius: radius.pill },
  dot: {
    position: 'absolute',
    width: 12,
    height: 12,
    borderRadius: 6,
    marginLeft: -6,
    top: -4,
  },
  rowValue: { width: 34, textAlign: 'right' },
});

export default FlavorFingerprint;
