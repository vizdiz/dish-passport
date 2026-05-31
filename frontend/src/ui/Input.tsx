import React, { useState } from 'react';
import {
  StyleSheet,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';

import { useTheme } from '../theme/ThemeProvider';
import { radius, space, typography } from '../theme/tokens';
import { Text } from './Text';

interface Props extends TextInputProps {
  label?: string;
  containerStyle?: StyleProp<ViewStyle>;
}

/** Single- or multi-line text input. Hairline border, radius md, accent focus ring. */
export function Input({ label, containerStyle, multiline, style, ...rest }: Props) {
  const { c } = useTheme();
  const [focused, setFocused] = useState(false);

  return (
    <View style={containerStyle}>
      {label && (
        <Text variant="label" tone="muted" style={styles.label}>
          {label}
        </Text>
      )}
      <TextInput
        placeholderTextColor={c.hint}
        multiline={multiline}
        onFocus={(e) => {
          setFocused(true);
          rest.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          rest.onBlur?.(e);
        }}
        style={[
          styles.input,
          typography.body,
          {
            color: c.ink,
            backgroundColor: c.surface,
            borderColor: focused ? c.accent : c.hairline,
            borderWidth: focused ? 1.5 : StyleSheet.hairlineWidth,
            minHeight: multiline ? 88 : 48,
            textAlignVertical: multiline ? 'top' : 'center',
          },
          style,
        ]}
        {...rest}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  label: { marginBottom: space.xs },
  input: {
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
});

export default Input;
