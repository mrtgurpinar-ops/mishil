import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppState, Platform, useColorScheme } from 'react-native';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';
import { initRevenueCat } from '../features/subscription/revenuecat';
import { initMetaSdkAndActivateApp } from '../features/analytics/metaAppEvents';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 60 * 2,
    },
  },
});

export default function RootLayout() {
  const systemColorScheme = useColorScheme();
  const { isDarkMode, useSystemTheme, setIsDarkMode } = useAppStore();

  useEffect(() => {
    if (useSystemTheme && systemColorScheme) {
      setIsDarkMode(systemColorScheme === 'dark');
    }
  }, [systemColorScheme, useSystemTheme]);

  useEffect(() => {
    // RevenueCat native IAP köprüsü hazırla
    initRevenueCat().catch(() => {});

    // Android'de ATT diyaloğu bulunmadığı için Meta SDK'yı WebView yüklenmesini beklemeden
    // RootLayout mount anında hemen başlat ve ön plana dönüşlerde (AppState === 'active') oturum sinyalini yenile.
    // iOS'ta ise Apple Guideline 5.1.2(i) gereği ATT diyaloğu MishilUnifiedWebView hazır olduğunda tetiklenir.
    if (Platform.OS === 'android') {
      initMetaSdkAndActivateApp().catch(() => {});
    }
    const sub = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'active' && Platform.OS === 'android') {
        initMetaSdkAndActivateApp().catch(() => {});
      }
    });
    return () => {
      sub.remove();
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        {/* Tekil Kod Tabanı: Tüm arayüz app.html üzerinde çalışır */}
        <StatusBar style="light" backgroundColor="#0B0E17" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: '#0B0E17' },
            animation: 'none',
          }}
        >
          {/* Ana giriş noktası — MishilUnifiedWebView */}
          <Stack.Screen name="index" options={{ headerShown: false }} />
          {/* Kilit ekranı Live Activity / bildirim deep-link ve eşleşmeyen rota koruması */}
          <Stack.Screen name="sleep" options={{ headerShown: false }} />
          <Stack.Screen name="+not-found" options={{ headerShown: false }} />
          {/* Eski rotalar — geçiş dönemi için korunur, aktif kullanılmaz */}
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="(auth)" options={{ headerShown: false }} />
          <Stack.Screen name="(onboarding)" options={{ headerShown: false }} />
          <Stack.Screen name="(paywall)" options={{ presentation: 'modal' }} />
          <Stack.Screen name="(preview)" options={{ headerShown: false }} />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
