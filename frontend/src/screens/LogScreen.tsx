import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { uploadPhoto } from '../api/client';
import { useLogDish } from '../api/hooks';
import type { LogResponse, Sentiment } from '../api/types';
import { DishCard } from '../components/DishCard';
import { SentimentControl } from '../components/SentimentControl';
import { useTheme } from '../theme/ThemeProvider';
import { radius, space } from '../theme/tokens';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Text } from '../ui/Text';

export function LogScreen() {
  const insets = useSafeAreaInsets();
  const { c } = useTheme();
  const logDish = useLogDish();

  const [text, setText] = useState('');
  const [sentiment, setSentiment] = useState<Sentiment>('liked');
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<LogResponse | null>(null);
  const [resultPhoto, setResultPhoto] = useState<string | null>(null);

  const pickPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7 });
    if (!res.canceled && res.assets[0]) setPhotoUri(res.assets[0].uri);
  };

  const submit = async () => {
    if (!text.trim()) return;
    setResult(null);
    const localPhoto = photoUri;
    let photo_url: string | undefined;
    try {
      if (photoUri) {
        setUploading(true);
        photo_url = await uploadPhoto(photoUri);
      }
    } catch {
      // upload failed — still log the dish, just without a photo
    } finally {
      setUploading(false);
    }
    logDish.mutate(
      { text: text.trim(), sentiment, photo_url },
      {
        onSuccess: (data) => {
          setResult(data);
          setResultPhoto(localPhoto);
          setText('');
          setPhotoUri(null);
          setSentiment('liked');
        },
      },
    );
  };

  const busy = uploading || logDish.isPending;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.paper }}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + space.lg }]}
      keyboardShouldPersistTaps="handled"
    >
      <Text variant="display">Log a dish</Text>
      <Text variant="body" tone="muted">
        Describe what you ate — we’ll match it to the canonical dish or create it.
      </Text>

      <Input
        label="What did you eat?"
        placeholder="e.g. spicy green papaya salad"
        value={text}
        onChangeText={setText}
        multiline
        containerStyle={styles.field}
      />

      <Text variant="label" tone="muted" style={styles.fieldLabel}>
        How was it?
      </Text>
      <SentimentControl value={sentiment} onChange={setSentiment} />

      <Text variant="label" tone="muted" style={styles.fieldLabel}>
        Photo (optional)
      </Text>
      <Pressable
        onPress={() => void pickPhoto()}
        style={[styles.photoBtn, { borderColor: c.hairline, backgroundColor: c.surface }]}
      >
        {photoUri ? (
          <Image source={{ uri: photoUri }} style={styles.photo} contentFit="cover" />
        ) : (
          <Text variant="body" tone="hint">
            ＋ Add a photo
          </Text>
        )}
      </Pressable>

      <Button
        title={uploading ? 'Uploading photo…' : 'Log it'}
        onPress={() => void submit()}
        loading={busy}
        disabled={!text.trim()}
        style={styles.submit}
      />

      {result ? (
        <View style={styles.result}>
          <Text variant="label" tone={result.is_new ? 'deep' : 'muted'}>
            {result.is_new ? 'New to the catalog' : 'Matched an existing dish'} · #{result.dish.id}
          </Text>
          <DishCard dish={result.dish} photoUrl={resultPhoto} />
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.sm, paddingBottom: space['3xl'] },
  field: { marginTop: space.md },
  fieldLabel: { marginTop: space.md },
  photoBtn: {
    height: 96,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  photo: { width: '100%', height: '100%' },
  submit: { marginTop: space.lg },
  result: { marginTop: space.xl, gap: space.sm },
});

export default LogScreen;
