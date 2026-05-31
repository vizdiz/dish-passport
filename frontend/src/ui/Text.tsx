import React from 'react';
import { Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { useTheme, type Palette } from '../theme/ThemeProvider';
import { tabularNumbers, typography, type TypeVariant } from '../theme/tokens';

export type Tone = keyof Palette;

interface Props extends RNTextProps {
  variant?: TypeVariant;
  tone?: Tone;
  /** Explicit color (e.g. a flavor ink) overriding `tone`. */
  color?: string;
  /** Tabular figures — use for all numbers so they align. */
  tabular?: boolean;
  center?: boolean;
}

/**
 * Typographic primitive. `variant` picks the type-scale entry (font family, size,
 * line-height, weight, tracking); `tone`/`color` pick the color from the active palette.
 */
export function Text({
  variant = 'body',
  tone = 'ink',
  color,
  tabular = false,
  center = false,
  style,
  ...rest
}: Props) {
  const { c } = useTheme();
  return (
    <RNText
      style={[
        typography[variant],
        { color: color ?? c[tone] },
        tabular && tabularNumbers,
        center && { textAlign: 'center' },
        style,
      ]}
      {...rest}
    />
  );
}

export default Text;
