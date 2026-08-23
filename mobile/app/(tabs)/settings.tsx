import React, { useState } from 'react';
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
import { VersionChangelogModal } from '../../components/VersionChangelogModal';
import { useSubscriptionStatus } from '../../features/subscription/hooks/useSubscriptionStatus';
import { triggerHaptic } from '../../lib/haptics';

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

  const [changelogVisible, setChangelogVisible] = useState(false);

  const handleLogout = async () => {
    triggerHaptic('warning');
    await logout();
    router.replace('/(auth)/login');
  };

  const handleToggleDark = () => {
    triggerHaptic('selection');
    toggleTheme();
  };

  const handleToggleSystem = (val: boolean) => {
    triggerHaptic('selection');
    setUseSystemTheme(val);
  };

  const openChangelog = () => {
    triggerHaptic('light');
    setChangelogVisible(true);
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Ayarlar
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          Uygulama tercihleri ve bebek profili
        </Text>
      </View>

      {/* 1. GRUP: Bebek Profili & Aile Paylaşımı */}
      <Text style={[styles.groupTitle, { color: theme.colors.textMuted }]}>
        BEBEK VE AİLE
      </Text>
      <Card style={styles.sectionCard}>
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
                ? `${activeBaby.age_in_months} Aylık • SweetSpot Aktif`
                : 'Yaş bilgisi yok'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => router.push('/(onboarding)/baby-profile')}
            style={[styles.editBtn, { borderColor: theme.colors.border }]}
          >
            <Text style={[styles.editBtnText, { color: theme.colors.accent }]}>
              Düzenle
            </Text>
          </TouchableOpacity>
        </View>

        <View style={[styles.divider, { backgroundColor: theme.colors.border }]} />

        <View style={styles.familyCodeRow}>
          <View>
            <Text style={[styles.familyCodeLabel, { color: theme.colors.textMuted }]}>
              Aile Paylaşım Kodu
            </Text>
            <Text style={[styles.familyCodeVal, { color: theme.colors.heading }]}>
              MISHIL-8492
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => triggerHaptic('success')}
            style={[styles.shareBadge, { backgroundColor: theme.isDark ? '#25304C' : '#E8EDF5' }]}
          >
            <Text style={[styles.shareBadgeText, { color: theme.colors.accent }]}>
              Kodu Kopyala
            </Text>
          </TouchableOpacity>
        </View>
      </Card>

      {/* 2. GRUP: Görünüm & Deneyim */}
      <Text style={[styles.groupTitle, { color: theme.colors.textMuted }]}>
        DENEYİM & GÖRÜNÜM
      </Text>
      <Card style={styles.sectionCard}>
        <View style={styles.settingRow}>
          <View style={styles.settingTextWrap}>
            <Text style={[styles.settingLabel, { color: theme.colors.heading }]}>
              Karanlık Mod (Gece Uykusu)
            </Text>
            <Text style={[styles.settingSub, { color: theme.colors.textMuted }]}>
              Melatonin salgısını koruyan düşük lümen
            </Text>
          </View>
          <Switch
            value={isDarkMode}
            onValueChange={handleToggleDark}
            trackColor={{ false: '#767577', true: theme.colors.accent }}
            thumbColor={isDarkMode ? '#FFFFFF' : '#f4f3f4'}
          />
        </View>

        <View style={[styles.divider, { backgroundColor: theme.colors.border }]} />

        <View style={styles.settingRow}>
          <View style={styles.settingTextWrap}>
            <Text style={[styles.settingLabel, { color: theme.colors.heading }]}>
              Sistem Temasını Takip Et
            </Text>
            <Text style={[styles.settingSub, { color: theme.colors.textMuted }]}>
              Cihaz saatine göre otomatik geçiş
            </Text>
          </View>
          <Switch
            value={useSystemTheme}
            onValueChange={handleToggleSystem}
            trackColor={{ false: '#767577', true: theme.colors.accent }}
            thumbColor={useSystemTheme ? '#FFFFFF' : '#f4f3f4'}
          />
        </View>
      </Card>

      {/* 3. GRUP: Abonelik & Güvenlik */}
      <Text style={[styles.groupTitle, { color: theme.colors.textMuted }]}>
        ABONELİK & HESAP
      </Text>
      <Card style={styles.sectionCard}>
        <View style={styles.subStatusRow}>
          <View style={{ flex: 1, marginRight: 10 }}>
            <Text style={[styles.subPlan, { color: theme.colors.heading }]}>
              {isTrial ? '3 Günlük Ücretsiz Deneme' : 'Mishil Yıllık Premium'}
            </Text>
            <Text style={[styles.subDesc, { color: theme.colors.textMuted }]}>
              {isTrial
                ? `Denemenin bitmesine ${daysLeftInTrial} gün kaldı.`
                : 'Tüm özellikler sınırsız aktif.'}
            </Text>
          </View>
          <Button
            title="Yönet"
            size="sm"
            onPress={() => router.push('/(paywall)/subscription')}
          />
        </View>

        <View style={[styles.divider, { backgroundColor: theme.colors.border }]} />

        <View style={styles.accountRow}>
          <Text style={[styles.accountLabel, { color: theme.colors.textMuted }]}>
            Giriş Yapılan Hesap:
          </Text>
          <Text style={[styles.accountEmail, { color: theme.colors.heading }]}>
            {user?.email || 'demo@mishil.app'}
          </Text>
        </View>

        <Button
          title="Oturumu Kapat"
          variant="danger"
          size="sm"
          onPress={handleLogout}
          style={{ marginTop: 12 }}
        />
      </Card>

      {/* 4. GRUP: Sürüm & Bilgi (Decluttered Minimal Footer) */}
      <TouchableOpacity
        onPress={openChangelog}
        style={[
          styles.versionBadgeRow,
          {
            backgroundColor: theme.colors.card,
            borderColor: theme.colors.border,
          },
        ]}
      >
        <View style={styles.versionBadgeLeft}>
          <Text style={styles.versionBadgeIcon}>✨</Text>
          <View>
            <Text style={[styles.versionBadgeTitle, { color: theme.colors.heading }]}>
              Mishil Baby v4.3.0
            </Text>
            <Text style={[styles.versionBadgeSub, { color: theme.colors.textMuted }]}>
              Neler Yeni? (Sürüm Notları ve Geliştirme Günlüğü)
            </Text>
          </View>
        </View>
        <Text style={[styles.versionArrow, { color: theme.colors.accent }]}>
          İncele ›
        </Text>
      </TouchableOpacity>

      <Text style={[styles.legalText, { color: theme.colors.textMuted }]}>
        Mishil Baby bir medikal teşhis aracı değildir. Pediatrik kılavuzluk sunar.
      </Text>

      {/* What's New & Changelog Modal */}
      <VersionChangelogModal
        visible={changelogVisible}
        onClose={() => setChangelogVisible(false)}
      />
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
    paddingBottom: 60,
  },
  header: {
    marginBottom: 20,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  groupTitle: {
    fontSize: 11,
    fontFamily: 'Inter',
    fontWeight: '700',
    letterSpacing: 0.8,
    marginBottom: 8,
    marginLeft: 4,
  },
  sectionCard: {
    marginBottom: 20,
    padding: 16,
    borderRadius: 20,
  },
  profileRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  avatarText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#141B2E',
  },
  profileInfo: {
    flex: 1,
  },
  babyName: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  babyAge: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  editBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    borderWidth: 1,
  },
  editBtnText: {
    fontSize: 11,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  divider: {
    height: 1,
    marginVertical: 12,
    opacity: 0.5,
  },
  familyCodeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  familyCodeLabel: {
    fontSize: 11,
    fontFamily: 'Inter',
  },
  familyCodeVal: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginTop: 2,
  },
  shareBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  shareBadgeText: {
    fontSize: 11,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  settingTextWrap: {
    flex: 1,
    marginRight: 10,
  },
  settingLabel: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  settingSub: {
    fontSize: 12,
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
  accountRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  accountLabel: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
  accountEmail: {
    fontSize: 13,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  versionBadgeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 18,
    borderWidth: 1,
    marginBottom: 16,
  },
  versionBadgeLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  versionBadgeIcon: {
    fontSize: 22,
    marginRight: 12,
  },
  versionBadgeTitle: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  versionBadgeSub: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  versionArrow: {
    fontSize: 13,
    fontFamily: 'Inter',
    fontWeight: '700',
    marginLeft: 8,
  },
  legalText: {
    fontSize: 11,
    fontFamily: 'Inter',
    textAlign: 'center',
    lineHeight: 16,
    paddingHorizontal: 20,
  },
});
