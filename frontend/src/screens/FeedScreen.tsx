import React, { useCallback, useRef, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, View, type ViewToken } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useLogDish, useRecommendations } from '../api/hooks';
import type { RecommendationItem, Sentiment } from '../api/types';
import { DishCard } from '../components/DishCard';
import { DishDetailSheet } from '../components/DishDetailSheet';
import { useImpressions } from '../store/impressions';
import { useTheme } from '../theme/ThemeProvider';
import { space } from '../theme/tokens';
import { Skeleton } from '../ui/Skeleton';
import { Text } from '../ui/Text';

const VIEWABILITY = { itemVisiblePercentThreshold: 50, minimumViewTime: 1000 };

export function FeedScreen() {
  const insets = useSafeAreaInsets();
  const { c } = useTheme();
  const { data, isLoading, isError, refetch, isRefetching } = useRecommendations(12);
  const flush = useImpressions((s) => s.flush);
  const logDish = useLogDish();

  const [sentiments, setSentiments] = useState<Record<number, Sentiment>>({});
  const [detailId, setDetailId] = useState<number | null>(null);

  const onSentiment = useCallback(
    (dishId: number, sentiment: Sentiment) => {
      setSentiments((prev) => ({ ...prev, [dishId]: sentiment }));
      logDish.mutate({ dish_id: dishId, sentiment });
    },
    [logDish],
  );

  // Stable across renders — FlatList requires it. Reads live state via getState().
  const onViewableItemsChanged = useRef((info: { viewableItems: ViewToken[] }) => {
    const now = new Date().toISOString();
    const track = useImpressions.getState().track;
    info.viewableItems.forEach((vt) => {
      const item = vt.item as RecommendationItem | undefined;
      if (item?.dish) {
        track({ dish_id: item.dish.id, shown_at: now, context: 'recs', converted: false });
      }
    });
  }).current;

  return (
    <View style={{ flex: 1, backgroundColor: c.paper }}>
      <FlatList
        data={data?.recommendations ?? []}
        keyExtractor={(item) => String(item.dish.id)}
        renderItem={({ item }) => (
          <DishCard
            dish={item.dish}
            explanation={item.explanation}
            sentiment={sentiments[item.dish.id]}
            onChangeSentiment={(s) => onSentiment(item.dish.id, s)}
            onPress={() => setDetailId(item.dish.id)}
          />
        )}
        contentContainerStyle={[styles.list, { paddingTop: insets.top + space.md }]}
        showsVerticalScrollIndicator={false}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={VIEWABILITY}
        onMomentumScrollEnd={() => void flush()}
        onScrollEndDrag={() => void flush()}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} tintColor={c.accent} />
        }
        ListHeaderComponent={
          <View style={styles.header}>
            <Text variant="display">For you</Text>
            {data?.cold_start ? (
              <Text variant="body" tone="muted">
                Getting to know your taste — log a few dishes to sharpen these.
              </Text>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          isLoading ? (
            <View style={{ gap: space.lg }}>
              <Skeleton height={280} radius={16} />
              <Skeleton height={280} radius={16} />
            </View>
          ) : isError ? (
            <Text variant="body" tone="muted">
              Couldn’t load recommendations. Pull to retry.
            </Text>
          ) : (
            <Text variant="body" tone="muted">
              No recommendations yet — log a dish to get started.
            </Text>
          )
        }
      />
      <DishDetailSheet dishId={detailId} onClose={() => setDetailId(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  list: { padding: space.lg, gap: space.lg },
  header: { gap: space.xs, marginBottom: space.sm },
});

export default FeedScreen;
