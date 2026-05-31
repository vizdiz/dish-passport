import { Ionicons } from '@expo/vector-icons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import React from 'react';

import { FeedScreen } from '../screens/FeedScreen';
import { LogScreen } from '../screens/LogScreen';
import { TasteScreen } from '../screens/TasteScreen';
import { useTheme } from '../theme/ThemeProvider';
import { fonts } from '../theme/tokens';

const Tab = createBottomTabNavigator();

type IconName = React.ComponentProps<typeof Ionicons>['name'];
const ICONS: Record<string, IconName> = {
  Feed: 'sparkles-outline',
  Log: 'add-circle-outline',
  Taste: 'person-outline',
};

export function RootTabs() {
  const { c } = useTheme();
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: c.accent,
        tabBarInactiveTintColor: c.hint,
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.hairline },
        tabBarLabelStyle: { fontFamily: fonts.hanken[500], fontSize: 11 },
        tabBarIcon: ({ color, size }) => (
          <Ionicons name={ICONS[route.name] ?? 'ellipse-outline'} size={size} color={color} />
        ),
      })}
    >
      <Tab.Screen name="Feed" component={FeedScreen} />
      <Tab.Screen name="Log" component={LogScreen} />
      <Tab.Screen name="Taste" component={TasteScreen} />
    </Tab.Navigator>
  );
}

export default RootTabs;
