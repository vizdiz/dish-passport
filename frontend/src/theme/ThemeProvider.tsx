import React, { createContext, useContext, useMemo } from 'react';
import { useColorScheme } from 'react-native';

import { color, colorDark, type ColorScheme } from './tokens';

// Both palettes share the same keys; widen the values to `string` so light/dark are
// interchangeable (the literal hex types differ).
export type Palette = Record<keyof typeof color, string>;

interface ThemeValue {
  scheme: ColorScheme;
  c: Palette;
}

const ThemeContext = createContext<ThemeValue>({ scheme: 'light', c: color });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const value = useMemo<ThemeValue>(() => {
    const scheme: ColorScheme = system === 'dark' ? 'dark' : 'light';
    return { scheme, c: scheme === 'dark' ? colorDark : color };
  }, [system]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
