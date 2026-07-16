import React, { useRef } from 'react';
import { Animated, Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';

import { motion } from '../theme/tokens';
import { useReducedMotion } from './useReducedMotion';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

interface Props extends Omit<PressableProps, 'style'> {
  style?: StyleProp<ViewStyle>;
  /** Scale to spring to while pressed (default 0.96). */
  scaleTo?: number;
}

/**
 * A Pressable that springs down on press and back on release — the `press` motion token.
 * Honors reduce-motion (no scale). Runs on the native driver.
 */
export function PressableScale({ style, scaleTo = motion.pressScale, onPressIn, onPressOut, children, ...rest }: Props) {
  const scale = useRef(new Animated.Value(1)).current;
  const reduced = useReducedMotion();
  const spring = (toValue: number) =>
    Animated.spring(scale, { toValue, useNativeDriver: true, ...motion.press }).start();
  return (
    <AnimatedPressable
      style={[style, { transform: [{ scale }] }]}
      onPressIn={(e) => {
        if (!reduced) spring(scaleTo);
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        if (!reduced) spring(1);
        onPressOut?.(e);
      }}
      {...rest}
    >
      {children}
    </AnimatedPressable>
  );
}

export default PressableScale;
