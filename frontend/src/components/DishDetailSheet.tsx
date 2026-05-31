import { Image } from 'expo-image';
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useDish, useSimilar } from '../api/hooks';
import type { FactorScore, SimilarNeighbor } from '../api/types';
import { useTheme } from '../theme/ThemeProvider';
import { radius, space } from '../theme/tokens';
import { BottomSheet } from '../ui/BottomSheet';
import { Chip } from '../ui/Chip';
import { Skeleton } from '../ui/Skeleton';
import { Text } from '../ui/Text';
import { FlavorFingerprint } from './FlavorFingerprint';

interface Props {
  dishId: number | null;
  onClose: () => void;
  onSelectDish?: (dishId: number) => void;
}

/** Dish detail as a sheet: lollipop fingerprint (Service 3) + similar dishes (Service 2). */
export function DishDetailSheet({ dishId, onClose, onSelectDish }: Props) {
  const visible = dishId !== null;
  const { data: dish, isLoading } = useDish(dishId ?? NaN);
  const { data: similar } = useSimilar(dishId ?? NaN, 6);
  const { c } = useTheme();

  return (
    <BottomSheet visible={visible} onClose={onClose} title={dish?.name ?? 'Dish'}>
      {isLoading || !dish ? (
        <Skeleton height={120} />
      ) : (
        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          {dish.description ? (
            <Text variant="body" tone="muted" style={styles.desc}>
              {dish.description}
            </Text>
          ) : null}

          <Text variant="label" tone="hint" style={styles.section}>
            FLAVOR
          </Text>
          <FlavorFingerprint scores={dish.flavor} variant="lollipop" />

          {dish.factors && dish.factors.length > 0 ? (
            <>
              <Text variant="label" tone="hint" style={styles.section}>
                TASTE FACTORS
              </Text>
              <View style={styles.factors}>
                {dish.factors.map((f: FactorScore) => (
                  <Chip
                    key={f.label}
                    label={f.label}
                    bg={c.hairline}
                    fg={c.muted}
                    score={f.value}
                  />
                ))}
              </View>
            </>
          ) : null}

          {similar && similar.neighbors.length > 0 ? (
            <>
              <Text variant="label" tone="hint" style={styles.section}>
                SIMILAR DISHES
              </Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.similarRow}>
                {similar.neighbors.map((nb: SimilarNeighbor) => (
                  <View key={nb.dish.id} style={styles.similar}>
                    <Image source={{ uri: '' }} style={[styles.similarPhoto, { backgroundColor: c.hairline }]} />
                    <Text variant="caption" numberOfLines={1}>
                      {nb.dish.name}
                    </Text>
                    <Text variant="micro" tone="hint" tabular>
                      {nb.cosine.toFixed(2)}
                    </Text>
                  </View>
                ))}
              </ScrollView>
            </>
          ) : null}
        </ScrollView>
      )}
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  scroll: { maxHeight: 480 },
  desc: { marginBottom: space.md },
  section: { marginTop: space.lg, marginBottom: space.sm, letterSpacing: 0.5 },
  factors: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  similarRow: { gap: space.md, paddingVertical: space.xs },
  similar: { width: 110, gap: 4 },
  similarPhoto: { width: 110, height: 82, borderRadius: radius.md },
});

export default DishDetailSheet;
