import React, { useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { motion } from '../theme/tokens';
import { useTheme } from '../theme/ThemeProvider';
import { radius, space } from '../theme/tokens';
import { Text } from './Text';
import { useReducedMotion } from './useReducedMotion';

type Variant = 'primary' | 'secondary' | 'ghost';

interface Props {
  title: string;
  onPress?: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

/** primary = paprika fill · secondary = paprika outline · ghost = text only. 48 tall, springs on press. */
export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  style,
  testID,
}: Props) {
  const { c } = useTheme();
  const isDisabled = disabled || loading;
  const scale = useRef(new Animated.Value(1)).current;
  const reduced = useReducedMotion();
  const spring = (toValue: number) =>
    Animated.spring(scale, { toValue, useNativeDriver: true, ...motion.press }).start();

  const box = (pressed: boolean): ViewStyle => {
    if (variant === 'primary') return { backgroundColor: pressed ? c.accentPress : c.accent };
    if (variant === 'secondary') {
      return { borderWidth: 1, borderColor: c.accent, backgroundColor: pressed ? c.hairline : 'transparent' };
    }
    return { backgroundColor: 'transparent', opacity: pressed ? 0.6 : 1 };
  };

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={isDisabled}
      onPressIn={() => !isDisabled && !reduced && spring(motion.pressScale)}
      onPressOut={() => !reduced && spring(1)}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      style={style}
    >
      {({ pressed }) => (
        <Animated.View
          style={[styles.base, box(pressed), { opacity: isDisabled ? 0.45 : (box(pressed).opacity ?? 1), transform: [{ scale }] }]}
        >
          {loading ? (
            <ActivityIndicator color={variant === 'primary' ? '#FFFFFF' : c.accent} />
          ) : (
            <View style={styles.row}>
              <Text variant="title" color={variant === 'primary' ? '#FFFFFF' : c.accent}>
                {title}
              </Text>
            </View>
          )}
        </Animated.View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
});

export default Button;
