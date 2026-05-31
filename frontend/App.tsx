// Root component. The full provider tree (SafeArea, QueryClient, Theme, User, Navigation)
// is assembled once the screens exist — see the end of the frontend build. Placeholder for now.
import React from 'react';
import { Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';

export default function App() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FBF7F0' }}>
      <Text style={{ color: '#2A2320' }}>Dish Passport</Text>
      <StatusBar style="auto" />
    </View>
  );
}
