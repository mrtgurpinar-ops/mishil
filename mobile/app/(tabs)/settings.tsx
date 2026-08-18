import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { useSubscriptionStatus } from '../../features/subscription/hooks/useSubscriptionStatus';

export default function SettingsScreen() {
  const router = useRouter();
  const {
    isDarkMode,
    useSystemTheme,
    toggleTheme,
    setUseSystemTheme,
    activeBaby,
    logout,
    user,
  } = useAppStore();
  const theme = getTheme(isDarkMode);
  const { subscription, isTrial, daysLeftInTrial } = useSubscriptionStatus();

  const handleLogout = async () => {
    await logout();
    router.replace('/(auth)/login');
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
    >
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Ayarlar
        </Text>
      </View>

      {/* Baby Profile Card */}
      <Card style={styles.sectionCard}>
        <Text style={[styles.sectionHeading, { color: theme.colors.heading }]}>
          Bebek Profili
        </Text>
        <View style={styles.profileRow}>
          <View
            style={[styles.avatar, { backgroundColor: theme.colors.accent }]}
          >
            <Text style={styles.avatarText}>
              {activeBaby?.name ? activeBaby.name.charAt(0).toUpperCase() : '👶'}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={[styles.babyName, { color: theme.colors.heading }]}>
              {activeBaby?.name || 'Bebek Tanımlanmadı'}
            </Text>
            <Text style={[styles.babyAge, { color: theme.colors.textMuted }]}>
              {activeBaby?.age_in_months
                ? `${activeBaby.age_in_months} Aylık`
                : 'Yaş bilgisi yok'}
            </Text>
          </View>
        </View>

        <Button
          title="+ Yeni Bebek Profili Ekle"
          variant="secondary"
          size="sm"
          onPress={() => router.push('/(onboarding)/baby-profile')}
          style={{ marginTop: 12 }}
        />
      </Card>

      {/* Subscription Card */}
      <Card style={styles.sectionCard}>
        <Text style={[styles.sectionHeading, { color: theme.colors.heading }]}>
          Abonelik Durumu
        </Text>
        <View style={styles.subStatusRow}>
          <View>
            <Text style={[styles.subPlan, { color: theme.colors.heading }]}>
              {isTrial ? '3 Günlük Ücretsiz Deneme' : 'Mishil Yıllık Premium'}
            </Text>
            <Text style={[styles.subDesc, { color: theme.colors.textMuted }]}>
              {isTrial
                ? `Deneme süresinin bitmesine ${daysLeftInTrial} gün kaldı.`
                : 'Tüm özellikler aktif.'}
            </Text>
          </View>
          <Button
            title="Yönet"
            size="sm"
            onPress={() => router.push('/(paywall)/subscription')}
          />
        </View>
      </Card>

      {/* Appearance & Theme */}
      <Card style={styles.sectionCard}>
        <Text style={[styles.sectionHeading, { color: theme.colors.heading }]}>
          Görünüm & Tema
        </Text>

        <View style={styles.settingRow}>
          <Text style={[styles.settingLabel, { color: theme.colors.text }]}>
            Karanlık Mod (Gece Uykusu)
          </Text>
          <Switch
            value={isDarkMode}
            onValueChange={toggleTheme}
            trackColor={{ false: '#767577', true: theme.colors.accent }}
            thumbColor={isDarkMode ? '#FFFFFF' : '#f4f3f4'}
          />
        </View>

        <View style={styles.settingRow}>
          <Text style={[styles.settingLabel, { color: theme.colors.text }]}>
            Sistem Temasını Takip Et
          </Text>
          <Switch
            value={useSystemTheme}
            onValueChange={setUseSystemTheme}
            trackColor={{ false: '#767577', true: theme.colors.accent }}
            thumbColor={useSystemTheme ? '#FFFFFF' : '#f4f3f4'}
          />
        </View>
      </Card>

      {/* App Info & Logout */}
      <Card style={styles.sectionCard}>
        <View style={styles.settingRow}>
          <Text style={[styles.settingLabel, { color: theme.colors.textMuted }]}>
            Giriş Yapılan Hesap
          </Text>
          <Text style={[styles.accountEmail, { color: theme.colors.heading }]}>
            {user?.email || 'demo@mishil.app'}
          </Text>
        </View>

        <Button
          title="Çıkış Yap"
          variant="danger"
          size="sm"
          onPress={handleLogout}
          style={{ marginTop: 16 }}
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
    padding: 20,
    paddingTop: 56,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  sectionCard: {
    marginBottom: 16,
    padding: 18,
  },
  sectionHeading: {
    fontSize: 16,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 14,
  },
  profileRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  avatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#141B2E',
  },
  profileInfo: {
    flex: 1,
  },
  babyName: {
    fontSize: 16,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  babyAge: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  subStatusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  subPlan: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  subDesc: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  settingLabel: {
    fontSize: 14,
    fontFamily: 'Inter',
  },
  accountEmail: {
    fontSize: 13,
    fontFamily: 'Inter',
    fontWeight: '500',
  },
});
