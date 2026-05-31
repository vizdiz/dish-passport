import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import type { Sentiment } from '../api/types';
import { useTheme } from '../theme/ThemeProvider';
import { radius, space } from '../theme/tokens';
import { Text } from '../ui/Text';

const SEGMENTS: { value: Sentiment; label: string }[] = [
  { value: 'liked', label: 'Like' },
  { value: 'neutral', label: 'Meh' },
  { value: 'disliked', label: 'Not for me' },
];

interface Props {
  value?: Sentiment;
  onChange: (s: Sentiment) => void;
}

/**
 * Three segments, each ≥48 tall. like/meh read neutral; "not for me" reads danger when
 * selected. THIS is the hard-negative emitter — one tap, one signal.
 */
export function SentimentControl({ value, onChange }: Props) {
  const { c } = useTheme();
  return (
    <View style={styles.row} accessibilityRole="radiogroup">
      {SEGMENTS.map((seg) => {
        const selected = value === seg.value;
        const danger = seg.value === 'disliked';
        const fg = selected ? (danger ? c.danger : c.ink) : c.muted;
        const borderColor = selected ? (danger ? c.danger : c.ink) : c.hairline;
        return (
          <Pressable
            key={seg.value}
            onPress={() => onChange(seg.value)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            style={[
              styles.segment,
              {
                borderColor,
                backgroundColor: selected && !danger ? c.surface : 'transparent',
                borderWidth: selected ? 1.5 : StyleSheet.hairlineWidth,
              },
            ]}
          >
            <Text variant="label" color={fg}>
              {seg.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: space.sm },
  segment: {
    flex: 1,
    minHeight: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.sm,
  },
});

export default SentimentControl;
