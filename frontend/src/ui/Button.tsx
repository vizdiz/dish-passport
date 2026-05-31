import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { useTheme } from '../theme/ThemeProvider';
import { radius, space, typography } from '../theme/tokens';
import { Text } from './Text';

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

/** primary = paprika fill · secondary = paprika outline · ghost = text only. 48 tall. */
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

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      style={({ pressed }) => {
        const base: ViewStyle = { ...styles.base, opacity: isDisabled ? 0.45 : 1 };
        if (variant === 'primary') {
          return [base, { backgroundColor: pressed ? c.accentPress : c.accent }, style];
        }
        if (variant === 'secondary') {
          return [
            base,
            { borderWidth: 1, borderColor: c.accent, backgroundColor: pressed ? c.hairline : 'transparent' },
            style,
          ];
        }
        return [base, { backgroundColor: 'transparent', opacity: pressed ? 0.6 : base.opacity }, style];
      }}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? '#FFFFFF' : c.accent} />
      ) : (
        <View style={styles.row}>
          <Text
            variant="title"
            color={variant === 'primary' ? '#FFFFFF' : c.accent}
            style={typography.title}
          >
            {title}
          </Text>
        </View>
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
