import React from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '../theme/ThemeProvider';
import { elevation, radius, space } from '../theme/tokens';

interface Props {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Set false to drop the default lg padding (e.g. a card whose photo bleeds to the edge). */
  padded?: boolean;
}

/** Surface, hairline border, radius lg(16), padding lg(16), near-invisible e1 elevation. */
export function Card({ children, style, padded = true }: Props) {
  const { c } = useTheme();
  return (
    <View
      style={[
        styles.card,
        elevation.e1,
        {
          backgroundColor: c.surface,
          borderColor: c.hairline,
          padding: padded ? space.lg : 0,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
});

export default Card;
