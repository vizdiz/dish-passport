import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '../api/client';
import { useTasteProfile } from '../api/hooks';
import type { Dish, FactorScore } from '../api/types';
import { Button } from '../ui/Button';
import { DishCard } from '../components/DishCard';
import { DishDetailSheet } from '../components/DishDetailSheet';
import { useSession } from '../store/session';
import { useTheme } from '../theme/ThemeProvider';
import { radius, space } from '../theme/tokens';
import { Skeleton } from '../ui/Skeleton';
import { Text } from '../ui/Text';

export function TasteScreen() {
  const insets = useSafeAreaInsets();
  const { c } = useTheme();
  const logout = useSession((s) => s.logout);
  const { data, isLoading, error } = useTasteProfile();
  const [detailId, setDetailId] = useState<number | null>(null);

  const notFound = error instanceof ApiError && error.status === 404;

  return (
    <View style={{ flex: 1, backgroundColor: c.paper }}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + space.lg }]}
        showsVerticalScrollIndicator={false}
      >
        <Text variant="display">Your taste</Text>

        {isLoading ? (
          <Skeleton height={120} radius={16} />
        ) : notFound || !data ? (
          <Text variant="body" tone="muted" style={styles.empty}>
            Log a few dishes and your taste profile will appear here.
          </Text>
        ) : (
          <>
            <Text variant="body" tone="muted">
              Built from {data.n_dishes} dish{data.n_dishes === 1 ? '' : 'es'} you’ve logged.
            </Text>

            {data.flavor_factor_pref && data.flavor_factor_pref.length > 0 ? (
              <View style={styles.section}>
                <Text variant="label" tone="hint" style={styles.sectionLabel}>
                  TASTE FACTORS
                </Text>
                {data.flavor_factor_pref.map((f: FactorScore) => (
                  <FactorBar key={f.label} label={f.label} value={f.value} />
                ))}
              </View>
            ) : null}

            {data.representative_dishes.length > 0 ? (
              <View style={styles.section}>
                <Text variant="label" tone="hint" style={styles.sectionLabel}>
                  DISHES THAT DEFINE YOU
                </Text>
                <View style={{ gap: space.lg }}>
                  {data.representative_dishes.map((d: Dish) => (
                    <DishCard key={d.id} dish={d} onPress={() => setDetailId(d.id)} />
                  ))}
                </View>
              </View>
            ) : null}
          </>
        )}

        <Button
          title="Log out"
          variant="ghost"
          onPress={() => void logout()}
          style={styles.logout}
        />
      </ScrollView>
      <DishDetailSheet dishId={detailId} onClose={() => setDetailId(null)} />
    </View>
  );
}

function FactorBar({ label, value }: { label: string; value: number }) {
  const { c } = useTheme();
  const mag = Math.min(1, Math.abs(value));
  const positive = value >= 0;
  return (
    <View style={styles.factorRow}>
      <Text variant="label" numberOfLines={1} style={styles.factorLabel}>
        {label}
      </Text>
      <View style={[styles.factorTrack, { backgroundColor: c.hairline }]}>
        <View
          style={[
            styles.factorFill,
            {
              width: `${mag * 100}%`,
              alignSelf: positive ? 'flex-start' : 'flex-end',
              backgroundColor: positive ? c.accent : c.deep,
            },
          ]}
        />
      </View>
      <Text variant="caption" tone="muted" tabular style={styles.factorValue}>
        {value.toFixed(2)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.sm, paddingBottom: space['3xl'] },
  logout: { marginTop: space['2xl'] },
  empty: { marginTop: space.lg },
  section: { marginTop: space.xl, gap: space.sm },
  sectionLabel: { letterSpacing: 0.5 },
  factorRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  factorLabel: { flex: 1 },
  factorTrack: { width: 120, height: 6, borderRadius: radius.pill, overflow: 'hidden' },
  factorFill: { height: 6, borderRadius: radius.pill },
  factorValue: { width: 40, textAlign: 'right' },
});

export default TasteScreen;
