import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { BreathingMoonIndicator } from '../../components/BreathingMoonIndicator';
import { useWakeWindow } from '../../features/wake-window/hooks/useWakeWindow';
import { requestNotificationPermissions } from '../../features/wake-window/notifications';

export default function WakeWindowSetupScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);

  const { calculate, wakeWindowData, isLoading } = useWakeWindow();
  const [permissionGranted, setPermissionGranted] = useState(false);

  useEffect(() => {
    if (activeBaby) {
      calculate({
        baby_age_months: activeBaby.age_in_months || 6,
        last_wake_time: new Date().toISOString(),
      });
    }
    requestNotificationPermissions().then(setPermissionGranted);
  }, [activeBaby]);

  const handleFinish = () => {
    router.replace('/(tabs)/home');
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
    >
      <View style={styles.header}>
        <Text style={styles.badge}>Adım 2 / 2</Text>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Uyku Ritmi Hazırlandı
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          {activeBaby?.name} için hesaplanan uyanıklık penceresi ve biyolojik uyku bütçesi:
        </Text>
      </View>

      {/* Signature Breathing Moon Indicator */}
      <BreathingMoonIndicator
        minutesLeft={wakeWindowData?.adjusted_wake_window_minutes || 120}
        label={`${wakeWindowData?.adjusted_wake_window_minutes || 120} Dk Uyanıklık Penceresi`}
        size={200}
      />

      <Card style={styles.card}>
        <View style={styles.metricRow}>
          <View style={styles.metricItem}>
            <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>
              Önerilen Uyanıklık
            </Text>
            <Text style={[styles.metricValue, { color: theme.colors.accent }]}>
              {wakeWindowData?.adjusted_wake_window_minutes || 120} dk
            </Text>
          </View>

          <View style={styles.metricItem}>
            <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>
              Günlük Nap Sayısı
            </Text>
            <Text style={[styles.metricValue, { color: theme.colors.heading }]}>
              {wakeWindowData?.recommended_daily_nap_count || 3} nap
            </Text>
          </View>
        </View>

        <View style={styles.adviceBox}>
          <Text style={[styles.adviceText, { color: theme.colors.text }]}>
            💡 {wakeWindowData?.advice ||
              'Bebeğinizi uyanıklık penceresi dolmadan 15 dakika önce loş odaya alıp sakinleştirici rutin başlatmanız tavsiye edilir.'}
          </Text>
        </View>

        <Button
          title="Mishil'i Kullanmaya Başla"
          onPress={handleFinish}
          loading={isLoading}
          style={styles.submitBtn}
        />
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    padding: 24,
    paddingTop: 50,
  },
  header: {
    alignItems: 'center',
    marginBottom: 16,
  },
  badge: {
    fontSize: 12,
    color: '#E8A855',
    fontFamily: 'Inter',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 6,
  },
  title: {
    fontSize: 26,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    fontFamily: 'Inter',
    textAlign: 'center',
    lineHeight: 20,
  },
  card: {
    padding: 20,
    marginTop: 12,
  },
  metricRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.08)',
  },
  metricItem: {
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 22,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  adviceBox: {
    padding: 12,
    borderRadius: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    marginBottom: 20,
  },
  adviceText: {
    fontSize: 13,
    fontFamily: 'Inter',
    lineHeight: 18,
  },
  submitBtn: {
    marginTop: 4,
  },
});
