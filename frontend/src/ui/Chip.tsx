import React from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { radius, space } from '../theme/tokens';
import { Text } from './Text';

interface Props {
  label: string;
  /** Background (e.g. a flavor `tint`). */
  bg: string;
  /** Foreground (e.g. a flavor `ink`). */
  fg: string;
  /** Optional trailing score, rendered in tabular figures. */
  score?: number;
  height?: number;
  style?: StyleProp<ViewStyle>;
}

/** Pill, height 24, padding 4/10. Used as the FlavorChip when fed a flavor tint/ink. */
export function Chip({ label, bg, fg, score, height = 24, style }: Props) {
  return (
    <View style={[styles.chip, { backgroundColor: bg, height, borderRadius: radius.pill }, style]}>
      <Text variant="caption" color={fg}>
        {label}
      </Text>
      {score !== undefined && (
        <Text variant="caption" color={fg} tabular style={styles.score}>
          {score.toFixed(2)}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingVertical: space.xs,
    paddingHorizontal: 10,
    gap: 6,
  },
  score: { opacity: 0.85 },
});

export default Chip;
