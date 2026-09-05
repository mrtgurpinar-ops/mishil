import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { format } from 'date-fns';
import { tr } from 'date-fns/locale';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { BreathingMoonIndicator } from '../../components/BreathingMoonIndicator';
import { useWakeWindow } from '../../features/wake-window/hooks/useWakeWindow';
import { useRoutines } from '../../features/routines/hooks/useRoutines';
import { triggerHaptic } from '../../lib/haptics';

const WONDER_WEEKS_LEAPS = [
  { num: 1, startWeek: 4, endWeek: 5, stormWeek: 5, title: 'Değişen Duyular', milestone: 'Dış dünyaya uyanış ve yoğun tensel temas ihtiyacı.', tip: 'Ortamı loş tutun, 432Hz ninniler açın.' },
  { num: 2, startWeek: 7, endWeek: 9, stormWeek: 8, title: 'Desenler & Kalıplar', milestone: 'El ve ayaklarını keşfeder, ritmik vücut hareketleri başlar.', tip: 'Aşırı uyarılmayı önlemek için SweetSpot pencerelerine uyun.' },
  { num: 3, startWeek: 11, endWeek: 12, stormWeek: 12, title: 'Yumuşak Geçişler', milestone: 'Ses tonlamalarını anlar, agu sesleriyle iletişim kurar.', tip: 'Yumuşak fısıltı ve su şırıltısı sesleri açın.' },
  { num: 4, startWeek: 15, endWeek: 19, stormWeek: 19, title: 'Olaylar & 4. Ay Regresyonu', milestone: 'Uyku döngüleri yetişkin tipine geçer, gece uyanmaları artar.', tip: 'Odayı tamamen karartın, 5S Dr. Karp Doğal Pışpış çalın.' },
  { num: 5, startWeek: 23, endWeek: 26, stormWeek: 26, title: 'İlişkiler & Mesafe', milestone: 'Ayrılık kaygısı başlar; annenin odadan çıkışını fark eder.', tip: 'Ce-eee oynayın, uykuya dalarken sırtını pışpışlayın.' },
  { num: 6, startWeek: 34, endWeek: 37, stormWeek: 37, title: 'Kategoriler Dünyası', milestone: 'Nesneleri sınıflandırır, emekleme ve diş çıkarma eşlik eder.', tip: 'Uyku öncesi diş etlerine soğuk masaj uygulayın.' },
  { num: 7, startWeek: 42, endWeek: 46, stormWeek: 46, title: 'Sıralar & Diziler', milestone: 'Kule yapma ve sıralı eylemleri anlama, uyku direnci.', tip: 'Sabit 3 adımlı uyku rutini uygulayın (Banyo -> Masaj -> Ninni).' },
  { num: 8, startWeek: 51, endWeek: 54, stormWeek: 53, title: 'Programlar Dünyası', milestone: 'Günlük hayat programlarını kavrar, hareketleri taklit eder.', tip: 'Ona seçim şansı verin, bağımsızlık hissi direnci kırar.' },
  { num: 9, startWeek: 60, endWeek: 64, stormWeek: 62, title: 'İlkeler Dünyası', milestone: 'Sınırları ve kuralları test eder, ilk inatlaşmalar başlar.', tip: 'Sakin ve net sınırlar koyun, kucaklayarak sakinleştirin.' },
  { num: 10, startWeek: 71, endWeek: 75, stormWeek: 74, title: 'Sistemler Dünyası', milestone: 'Benlik bilinci ve dil gelişimi büyük sıçrama yapar.', tip: 'Uyku öncesi gün değerlendirmesi yaparak rahatlatın.' },
];

export default function HomeScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);

  const { wakeWindowData, isLoading, refetch } = useWakeWindow();
  const { addRoutine } = useRoutines();
  const [refreshing, setRefreshing] = useState(false);

  // Live sleep tracking state
  const [isSleeping, setIsSleeping] = useState(false);
  const [sleepStartTimestamp, setSleepStartTimestamp] = useState<number | null>(null);
  const [elapsedSleepMinutes, setElapsedSleepMinutes] = useState(0);

  useEffect(() => {
    let timer: any;
    if (isSleeping && sleepStartTimestamp) {
      timer = setInterval(() => {
        const diffMins = Math.floor((Date.now() - sleepStartTimestamp) / 60000);
        setElapsedSleepMinutes(diffMins);
      }, 1000);
    } else {
      setElapsedSleepMinutes(0);
    }
    return () => clearInterval(timer);
  }, [isSleeping, sleepStartTimestamp]);

  const onRefresh = async () => {
    setRefreshing(true);
    triggerHaptic('light');
    await refetch();
    setRefreshing(false);
  };

  // Calculate remaining minutes to next sleep
  const getRemainingMinutes = () => {
    if (!wakeWindowData?.next_sleep_time) return 60;
    const target = new Date(wakeWindowData.next_sleep_time).getTime();
    const diff = Math.max(0, Math.round((target - Date.now()) / 60000));
    return diff;
  };

  const remainingMins = getRemainingMinutes();
  const nextSleepFormatted = wakeWindowData?.next_sleep_time
    ? format(new Date(wakeWindowData.next_sleep_time), 'HH:mm', { locale: tr })
    : '--:--';

  // Wonder Weeks Leap Calculation
  const babyAge = activeBaby?.age_in_months || 6;
  const babyWeeks = Math.max(1, Math.round(babyAge * 4.345));
  const activeLeap =
    WONDER_WEEKS_LEAPS.find((l) => babyWeeks <= l.endWeek) ||
    WONDER_WEEKS_LEAPS[WONDER_WEEKS_LEAPS.length - 1];
  const leapProgressPercent = Math.min(100, Math.round((babyWeeks / 75) * 100));
  const isStormPeak = babyWeeks === activeLeap.stormWeek;

  const handleStartSleep = () => {
    triggerHaptic('medium');
    setIsSleeping(true);
    setSleepStartTimestamp(Date.now());
  };

  const handleFinishSleep = async () => {
    triggerHaptic('success');
    const duration = Math.max(1, elapsedSleepMinutes);
    await addRoutine({
      routine_type: 'sleep',
      details: { duration_minutes: duration, live_tracked: true },
      notes: `${duration} dakikalık canlı uyku seansı tamamlandı.`,
    });
    setIsSleeping(false);
    setSleepStartTimestamp(null);
    router.push('/(tabs)/routines');
  };

  const handleQuickRoutine = async (type: string) => {
    triggerHaptic('medium');
    if (type === 'sleep') {
      handleStartSleep();
      return;
    }
    await addRoutine({
      routine_type: type,
      details: { quick_logged: true },
    });
    router.push('/(tabs)/routines');
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
      showsVerticalScrollIndicator={false}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={theme.colors.accent}
        />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={[styles.greeting, { color: theme.colors.textMuted }]}>
            {activeBaby ? `${activeBaby.name}'in Uyku Ritmi` : 'Mishil Baby'}
          </Text>
          <Text style={[styles.title, { color: theme.colors.heading }]}>
            {isSleeping
              ? `${elapsedSleepMinutes} dk Uykuda 💤`
              : remainingMins > 0
              ? `${remainingMins} dk Sonra Uyku`
              : 'Uyku Vakti!'}
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => {
            triggerHaptic('light');
            router.push('/(preview)/moon-preview');
          }}
          style={[styles.previewBadge, { borderColor: theme.colors.border }]}
        >
          <Text style={[styles.previewText, { color: theme.colors.accent }]}>
            İzole Mod
          </Text>
        </TouchableOpacity>
      </View>

      {/* Signature Breathing Moon Indicator */}
      <BreathingMoonIndicator
        minutesLeft={remainingMins}
        isSleeping={isSleeping}
        size={230}
        label={
          isSleeping
            ? `Derin Uyku Seansı (${elapsedSleepMinutes} dk)`
            : `Sıradaki Uyku: ${nextSleepFormatted}`
        }
      />

      {/* Live Sleep Controller Bar */}
      {isSleeping ? (
        <Card
          style={[
            styles.liveSleepCard,
            { backgroundColor: theme.isDark ? '#2D1F38' : '#F5EEF8' },
          ]}
        >
          <View style={styles.liveSleepTextWrap}>
            <Text style={[styles.liveSleepTitle, { color: '#A569BD' }]}>
              🌙 Canlı Uyku Seansı Devam Ediyor
            </Text>
            <Text style={[styles.liveSleepSub, { color: theme.colors.textMuted }]}>
              Bebek uyandığında kaydı sonlandırın.
            </Text>
          </View>
          <Button
            title="Uykuyu Bitir"
            size="sm"
            onPress={handleFinishSleep}
            style={{ backgroundColor: '#A569BD' }}
          />
        </Card>
      ) : null}

      {/* Overtired Warning Alert (if triggered) */}
      {!isSleeping && wakeWindowData?.is_overtired_risk ? (
        <View
          style={[
            styles.overtiredBanner,
            {
              backgroundColor: theme.isDark ? '#2D2015' : '#FFF3E0',
              borderColor: theme.colors.accent,
            },
          ]}
        >
          <Text style={styles.overtiredIcon}>⚠️</Text>
          <Text
            style={[
              styles.overtiredText,
              { color: theme.isDark ? '#F5C68A' : '#B76E00' },
            ]}
          >
            {wakeWindowData.overtired_explanation ||
              'Aşırı yorgunluk riski tespit edildi. Uyanıklık penceresi %15 kısaltıldı.'}
          </Text>
        </View>
      ) : null}

      {/* Sleep Window Projection Card */}
      <Card style={styles.infoCard}>
        <View style={styles.metricGrid}>
          <View style={styles.metricBox}>
            <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>
              Hedef Uyku Saati
            </Text>
            <Text style={[styles.metricValue, { color: theme.colors.accent }]}>
              {nextSleepFormatted}
            </Text>
          </View>

          <View style={styles.metricBox}>
            <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>
              Uyanıklık Penceresi
            </Text>
            <Text style={[styles.metricValue, { color: theme.colors.heading }]}>
              {wakeWindowData?.adjusted_wake_window_minutes || 120} dk
            </Text>
          </View>

          <View style={styles.metricBox}>
            <Text style={[styles.metricLabel, { color: theme.colors.textMuted }]}>
              Kalan Nap Sayısı
            </Text>
            <Text style={[styles.metricValue, { color: theme.colors.heading }]}>
              {wakeWindowData?.remaining_naps_plan?.length || 2} nap
            </Text>
          </View>
        </View>
      </Card>

      {/* Quick Action Shortcuts */}
      <Text style={[styles.sectionHeading, { color: theme.colors.heading }]}>
        Hızlı Rutin Ekle
      </Text>
      <View style={styles.quickActionRow}>
        {[
          { type: 'feeding', icon: '🍼', label: 'Beslenme' },
          { type: 'diaper', icon: '🚼', label: 'Alt Değiştirme' },
          {
            type: 'sleep',
            icon: isSleeping ? '⏹️' : '🌙',
            label: isSleeping ? 'Uykuyu Bitir' : 'Uyku Başlat',
          },
        ].map((act) => (
          <TouchableOpacity
            key={act.type}
            onPress={() => handleQuickRoutine(act.type)}
            activeOpacity={0.7}
            style={[
              styles.quickActionBtn,
              {
                backgroundColor:
                  act.type === 'sleep' && isSleeping
                    ? theme.isDark
                      ? '#3A2048'
                      : '#F2D7EE'
                    : theme.colors.card,
                borderColor:
                  act.type === 'sleep' && isSleeping
                    ? '#A569BD'
                    : theme.colors.border,
              },
            ]}
          >
            <Text style={styles.quickActionIcon}>{act.icon}</Text>
            <Text
              style={[
                styles.quickActionLabel,
                {
                  color:
                    act.type === 'sleep' && isSleeping
                      ? '#A569BD'
                      : theme.colors.heading,
                  fontWeight: act.type === 'sleep' && isSleeping ? '700' : '500',
                },
              ]}
            >
              {act.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Wonder Weeks & Klinik Gelişim Takibi Bento Kartı */}
      <Text style={[styles.sectionHeading, { color: theme.colors.heading }]}>
        Gelişim Takibi & Wonder Weeks
      </Text>
      <Card style={[styles.growthCard, { backgroundColor: theme.colors.card, borderColor: theme.colors.border }]}>
        <View style={styles.growthHeader}>
          <View style={{ flex: 1, marginRight: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <Text style={[styles.growthTitle, { color: theme.colors.heading }]}>
                {activeLeap.num}. Sıçrama: {activeLeap.title}
              </Text>
              {isStormPeak ? (
                <View style={styles.stormBadge}>
                  <Text style={styles.stormBadgeText}>⚡ Fırtına Zirvesi</Text>
                </View>
              ) : null}
            </View>
            <Text style={[styles.growthSub, { color: theme.colors.textMuted }]}>
              {activeBaby?.name || 'Bebeğiniz'} şu anda {babyWeeks}. haftasında • {activeLeap.startWeek}-{activeLeap.endWeek}. haftalar arası
            </Text>
          </View>
          <View style={[styles.scoreCircle, { borderColor: theme.colors.accent }]}>
            <Text style={[styles.scoreNum, { color: theme.colors.accent }]}>%84</Text>
            <Text style={[styles.scoreLabel, { color: theme.colors.textMuted }]}>Denge</Text>
          </View>
        </View>

        <Text style={[styles.milestoneText, { color: theme.colors.text }]}>
          🌱 {activeLeap.milestone}
        </Text>

        {/* Progress Bar */}
        <View style={[styles.progressBarTrack, { backgroundColor: theme.isDark ? '#25304C' : '#E8EDF5' }]}>
          <View
            style={[
              styles.progressBarFill,
              { width: `${leapProgressPercent}%`, backgroundColor: theme.colors.accent },
            ]}
          />
        </View>
        <Text style={[styles.progressDesc, { color: theme.colors.textMuted }]}>
          10 Zihinsel Sıçramadan %{leapProgressPercent} tamamlandı
        </Text>

        <View style={[styles.dadTipBox, { backgroundColor: theme.isDark ? '#1C263D' : '#F1F5FB' }]}>
          <Text style={[styles.dadTipText, { color: theme.colors.text }]}>
            💡 <Text style={{ fontWeight: '700' }}>Mışıl Dadı Tavsiyesi:</Text> {activeLeap.tip}
          </Text>
        </View>
      </Card>

      {/* Soothing Noise CTA */}
      <Card
        style={[
          styles.soundCtaCard,
          { backgroundColor: theme.isDark ? '#1C253D' : '#F0EBE1' },
        ]}
      >
        <View style={styles.soundCtaContent}>
          <Text style={styles.soundCtaIcon}>🎧</Text>
          <View style={styles.soundCtaText}>
            <Text style={[styles.soundCtaTitle, { color: theme.colors.heading }]}>
              432Hz Pembe Gürültü Başlat
            </Text>
            <Text style={[styles.soundCtaSub, { color: theme.colors.textMuted }]}>
              Derin uykuya geçişi hızlandıran sakinleştirici frekans.
            </Text>
          </View>
        </View>
        <Button
          title="Çal"
          size="sm"
          onPress={() => {
            triggerHaptic('light');
            router.push('/(tabs)/sounds');
          }}
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
    paddingBottom: 80,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  greeting: {
    fontSize: 13,
    fontFamily: 'Inter',
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginTop: 2,
  },
  previewBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
  },
  previewText: {
    fontSize: 11,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  liveSleepCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    borderRadius: 16,
    marginVertical: 10,
    borderWidth: 1,
    borderColor: '#A569BD',
  },
  liveSleepTextWrap: {
    flex: 1,
    marginRight: 10,
  },
  liveSleepTitle: {
    fontSize: 13,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  liveSleepSub: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  overtiredBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    marginVertical: 12,
  },
  overtiredIcon: {
    fontSize: 18,
    marginRight: 8,
  },
  overtiredText: {
    flex: 1,
    fontSize: 12,
    fontFamily: 'Inter',
    fontWeight: '500',
    lineHeight: 16,
  },
  infoCard: {
    marginTop: 12,
    marginBottom: 20,
    borderRadius: 20,
  },
  metricGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: 4,
  },
  metricBox: {
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 18,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  sectionHeading: {
    fontSize: 16,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 12,
  },
  quickActionRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  quickActionBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    borderRadius: 18,
    borderWidth: 1,
  },
  quickActionIcon: {
    fontSize: 24,
    marginBottom: 6,
  },
  quickActionLabel: {
    fontSize: 12,
    fontFamily: 'Inter',
    textAlign: 'center',
  },
  soundCtaCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderRadius: 20,
  },
  soundCtaContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 12,
  },
  soundCtaIcon: {
    fontSize: 26,
    marginRight: 12,
  },
  soundCtaText: {
    flex: 1,
  },
  soundCtaTitle: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  soundCtaSub: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  growthCard: {
    padding: 16,
    borderRadius: 20,
    borderWidth: 1,
    marginBottom: 20,
  },
  growthHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 10,
  },
  growthTitle: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  growthSub: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  stormBadge: {
    backgroundColor: 'rgba(231, 76, 60, 0.2)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  stormBadgeText: {
    color: '#E74C3C',
    fontSize: 10,
    fontFamily: 'Inter',
    fontWeight: '700',
  },
  scoreCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scoreNum: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  scoreLabel: {
    fontSize: 9,
    fontFamily: 'Inter',
  },
  milestoneText: {
    fontSize: 13,
    fontFamily: 'Inter',
    lineHeight: 18,
    marginBottom: 12,
  },
  progressBarTrack: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: 4,
  },
  progressBarFill: {
    height: '100%',
    borderRadius: 3,
  },
  progressDesc: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginBottom: 12,
  },
  dadTipBox: {
    padding: 12,
    borderRadius: 14,
  },
  dadTipText: {
    fontSize: 12,
    fontFamily: 'Inter',
    lineHeight: 16,
  },
});
