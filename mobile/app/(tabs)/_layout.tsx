import React from 'react';
import { Tabs } from 'expo-router';
import { Text, Platform, StyleSheet } from 'react-native';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';

export default function TabsLayout() {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: theme.isDark ? '#111728' : '#FFFFFF',
          borderTopColor: theme.colors.border,
          borderTopWidth: 1,
          height: Platform.OS === 'ios' ? 88 : 64,
          paddingBottom: Platform.OS === 'ios' ? 28 : 10,
          paddingTop: 8,
        },
        tabBarActiveTintColor: theme.colors.accent,
        tabBarInactiveTintColor: theme.colors.textMuted,
        tabBarLabelStyle: {
          fontSize: 11,
          fontFamily: 'Inter',
          fontWeight: '500',
        },
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: 'Ana Sayfa',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20 }}>🌙</Text>,
        }}
      />
      <Tabs.Screen
        name="coach"
        options={{
          title: 'Mışıl Dadı',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20 }}>👵</Text>,
        }}
      />
      <Tabs.Screen
        name="routines"
        options={{
          title: 'Rutinler',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20 }}>📋</Text>,
        }}
      />
      <Tabs.Screen
        name="sounds"
        options={{
          title: 'Sesler',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20 }}>🎵</Text>,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Ayarlar',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20 }}>⚙️</Text>,
        }}
      />
      <Tabs.Screen
        name="cry-analysis"
        options={{
          href: null, // Accessible via router.push('/(tabs)/cry-analysis')
        }}
      />
    </Tabs>
  );
}
