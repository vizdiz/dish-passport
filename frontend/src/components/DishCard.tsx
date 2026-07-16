import { Image } from 'expo-image';
import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';

import type { Dish, Sentiment } from '../api/types';
import { useTheme } from '../theme/ThemeProvider';
import { FLAVOR_DIMS, flavor, flavorInk, motion, radius, space, type FlavorDim } from '../theme/tokens';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { PressableScale } from '../ui/PressableScale';
import { Text } from '../ui/Text';
import { useReducedMotion } from '../ui/useReducedMotion';
import { FlavorFingerprint } from './FlavorFingerprint';
import { SentimentControl } from './SentimentControl';

interface Props {
  dish: Dish;
  photoUrl?: string | null;
  /** Flavor-factor explanation from the recommender (never derived from the embedding). */
  explanation?: string | null;
  sentiment?: Sentiment;
  onChangeSentiment?: (s: Sentiment) => void;
  onPress?: () => void;
}

function topFlavors(scores: Record<string, number>, n = 3): { dim: FlavorDim; value: number }[] {
  return FLAVOR_DIMS.map((dim) => ({ dim, value: scores[dim] ?? 0 }))
    .filter((x) => x.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, n);
}

/** The hero. Photo (4:3) · Inter name · spectrum fingerprint · top-3 flavor chips ·
 * optional explanation · optional sentiment control. Springs in on mount (`enter` token). */
export function DishCard({ dish, photoUrl, explanation, sentiment, onChangeSentiment, onPress }: Props) {
  const { scheme, c } = useTheme();
  const top = topFlavors(dish.flavor);
  const reduced = useReducedMotion();
  const enter = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reduced) {
      enter.setValue(1);
      return;
    }
    Animated.spring(enter, { toValue: 1, useNativeDriver: true, ...motion.enter }).start();
  }, [enter, reduced]);

  const enterStyle = {
    opacity: enter,
    transform: [
      { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [motion.enterTravel, 0] }) },
    ],
  };

  const content = (
    <Card padded={false}>
      {photoUrl ? (
        <Image source={{ uri: photoUrl }} style={styles.photo} contentFit="cover" transition={150} />
      ) : (
        <View style={[styles.photo, styles.placeholder, { backgroundColor: c.hairline }]}>
          <Text variant="caption" tone="hint">
            no photo yet
          </Text>
        </View>
      )}
      <View style={styles.body}>
        <Text variant="h1" numberOfLines={1} style={styles.name}>
          {dish.name}
        </Text>
        <FlavorFingerprint scores={dish.flavor} variant="spectrum" />
        <View style={styles.chips}>
          {top.map((t) => (
            <Chip
              key={t.dim}
              label={t.dim}
              bg={flavor[t.dim].tint}
              fg={flavorInk(t.dim, scheme)}
              score={t.value}
            />
          ))}
        </View>
        {explanation ? (
          <Text variant="caption" tone="muted">
            {explanation}
          </Text>
        ) : null}
        {onChangeSentiment ? (
          <SentimentControl value={sentiment} onChange={onChangeSentiment} />
        ) : null}
      </View>
    </Card>
  );

  return (
    <Animated.View style={enterStyle}>
      {onPress ? (
        <PressableScale onPress={onPress} accessibilityRole="button">
          {content}
        </PressableScale>
      ) : (
        content
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  photo: { width: '100%', aspectRatio: 4 / 3, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg },
  placeholder: { alignItems: 'center', justifyContent: 'center' },
  body: { padding: space.lg, gap: space.md },
  name: { fontSize: 20, lineHeight: 26 }, // Inter (h1), sized for a card
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
});

export default DishCard;
