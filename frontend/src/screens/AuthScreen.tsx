import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '../api/client';
import { useSession } from '../store/session';
import { useTheme } from '../theme/ThemeProvider';
import { space } from '../theme/tokens';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Text } from '../ui/Text';

export function AuthScreen() {
  const insets = useSafeAreaInsets();
  const { c } = useTheme();
  const login = useSession((s) => s.login);
  const register = useSession((s) => s.register);

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLogin = mode === 'login';

  const submit = async () => {
    setError(null);
    if (username.trim().length < 3 || password.length < 6) {
      setError('Username needs 3+ characters and password 6+.');
      return;
    }
    setBusy(true);
    try {
      if (isLogin) await login(username.trim(), password);
      else await register(username.trim(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ flex: 1, backgroundColor: c.paper }}
    >
      <View style={[styles.container, { paddingTop: insets.top + space['3xl'] }]}>
        <Text variant="display">Dish Passport</Text>
        <Text variant="body" tone="muted" style={styles.tagline}>
          {isLogin ? 'Welcome back.' : 'Track every dish, find your next favorite.'}
        </Text>

        <Input
          label="Username"
          autoCapitalize="none"
          autoCorrect={false}
          value={username}
          onChangeText={setUsername}
          placeholder="yourname"
          containerStyle={styles.field}
        />
        <Input
          label="Password"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          placeholder="••••••"
          containerStyle={styles.field}
        />

        {error ? (
          <Text variant="label" color={c.danger} style={styles.error}>
            {error}
          </Text>
        ) : null}

        <Button
          title={isLogin ? 'Log in' : 'Sign up'}
          onPress={() => void submit()}
          loading={busy}
          disabled={busy}
          style={styles.submit}
        />
        <Button
          title={isLogin ? 'New here? Create an account' : 'Have an account? Log in'}
          variant="ghost"
          onPress={() => {
            setMode(isLogin ? 'register' : 'login');
            setError(null);
          }}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: space.xl, gap: space.sm },
  tagline: { marginBottom: space.xl },
  field: { marginTop: space.md },
  error: { marginTop: space.md },
  submit: { marginTop: space.xl },
});

export default AuthScreen;
