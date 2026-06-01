import {
  Fraunces_400Regular,
  Fraunces_500Medium,
  Fraunces_600SemiBold,
} from '@expo-google-fonts/fraunces';
import {
  HankenGrotesk_400Regular,
  HankenGrotesk_500Medium,
  HankenGrotesk_600SemiBold,
  HankenGrotesk_700Bold,
} from '@expo-google-fonts/hanken-grotesk';
import { DarkTheme, DefaultTheme, NavigationContainer } from '@react-navigation/native';
import { QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { queryClient } from './src/api/queryClient';
import { RootTabs } from './src/navigation/RootTabs';
import { AuthScreen } from './src/screens/AuthScreen';
import { useSession } from './src/store/session';
import { ThemeProvider, useTheme } from './src/theme/ThemeProvider';
import { color } from './src/theme/tokens';

function Navigation() {
  const { c, scheme } = useTheme();
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  const navTheme = {
    ...base,
    colors: {
      ...base.colors,
      background: c.paper,
      card: c.surface,
      text: c.ink,
      border: c.hairline,
      primary: c.accent,
    },
  };
  return (
    <NavigationContainer theme={navTheme}>
      <RootTabs />
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
    </NavigationContainer>
  );
}

// Inside the providers: gate on the session. Splash while hydrating, Auth screen until a
// token exists, the tab app once signed in.
function Root() {
  const { c } = useTheme();
  const ready = useSession((s) => s.ready);
  const authenticated = useSession((s) => s.authenticated);
  if (!ready) return <View style={{ flex: 1, backgroundColor: c.paper }} />;
  return authenticated ? <Navigation /> : <AuthScreen />;
}

export default function App() {
  const [fontsLoaded] = useFonts({
    Fraunces_400Regular,
    Fraunces_500Medium,
    Fraunces_600SemiBold,
    HankenGrotesk_400Regular,
    HankenGrotesk_500Medium,
    HankenGrotesk_600SemiBold,
    HankenGrotesk_700Bold,
  });
  const hydrate = useSession((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  if (!fontsLoaded) {
    return <View style={{ flex: 1, backgroundColor: color.paper }} />;
  }

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <Root />
        </ThemeProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
