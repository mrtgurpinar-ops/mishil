import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';
import { Button } from './ui/Button';
import { triggerHaptic } from '../lib/haptics';

interface VersionChangelogModalProps {
  visible: boolean;
  onClose: () => void;
}

const CHANGELOG_HISTORY = [
  {
    version: 'v4.3.0 (Güncel)',
    date: '23 Ağustos 2026',
    title: 'UI/UX & Akustik Tasarım Mühendisliği Yükseltmesi',
    changes: [
      '✨ Canlı Uyku Modu & Dinamik Mor Nefes Alan Ay Dönüşümü',
      '⏱️ Sakinleştirici Sesler için Hızlı Kapanma Zamanlayıcısı (15m - 60m)',
      '📊 Rutinler Dikey Bento Zaman Çizelgesi & Günlük İstatistik Widgetları',
      '📱 Dokunsal Haptik Ergonomi (Expo-Haptics) & Tek Elle Kullanım Optimizasyonu',
      '⚙️ Sadeleştirilmiş Modüler Ayarlar Mimarisi & Sürüm Takipçisi',
    ],
  },
  {
    version: 'v4.2.0',
    date: '20 Ağustos 2026',
    title: 'Librosa DSP Akustik Ağlama Analizi',
    changes: [
      '🎙️ 13-Band MFCC, Spectral Centroid ve Zero-Crossing Rate ile Açlık/Gaz/Uyku Tespiti',
      '🔒 Apple 3.1.1 ve 5.1.1 Yasal Mağaza & Veri Güvenliği Uyumluluğu',
      '👥 Aile Paylaşım Kodu (MISHIL-8492) ile Çoklu Ebeveyn Eşitleme',
    ],
  },
  {
    version: 'v4.1.0',
    date: '15 Ağustos 2026',
    title: 'Dinamik Wake Window & SweetSpot Motoru',
    changes: [
      '🌙 0-36 Ay Pediatrik Uyanıklık Penceresi Algoritması',
      '⚠️ %15 Aşırı Yorgunluk (Overtired) Otomatik Süre Daraltma Koruması',
      '🎧 432Hz Pembe Gürültü ve Arka Planda Kesintisiz Çalma',
    ],
  },
];

export const VersionChangelogModal: React.FC<VersionChangelogModalProps> = ({
  visible,
  onClose,
}) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const handleClose = () => {
    triggerHaptic('light');
    onClose();
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      onRequestClose={handleClose}
    >
      <View style={styles.overlay}>
        <View
          style={[
            styles.card,
            {
              backgroundColor: theme.colors.card,
              borderColor: theme.colors.border,
            },
          ]}
        >
          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={[styles.title, { color: theme.colors.heading }]}>
                Sürüm & Geliştirme Günlüğü
              </Text>
              <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
                Mishil Baby Sürüm Notları
              </Text>
            </View>
            <TouchableOpacity onPress={handleClose} style={styles.closeBtn}>
              <Text style={[styles.closeText, { color: theme.colors.textMuted }]}>
                ✕
              </Text>
            </TouchableOpacity>
          </View>

          {/* Current Version Highlight Badge */}
          <View
            style={[
              styles.currentVersionBanner,
              { backgroundColor: theme.isDark ? '#25304C' : '#E8EDF5' },
            ]}
          >
            <Text style={{ fontSize: 24, marginRight: 10 }}>🚀</Text>
            <View>
              <Text style={[styles.bannerTitle, { color: theme.colors.heading }]}>
                Mishil Baby v4.3.0
              </Text>
              <Text style={[styles.bannerSub, { color: theme.colors.accent }]}>
                Build 2026.08 • En Son Güncel Sürüm
              </Text>
            </View>
          </View>

          {/* Scrollable Changelog List */}
          <ScrollView
            style={styles.changelogScroll}
            showsVerticalScrollIndicator={false}
          >
            {CHANGELOG_HISTORY.map((item, idx) => (
              <View
                key={idx}
                style={[
                  styles.versionBlock,
                  {
                    borderBottomColor: theme.colors.border,
                    borderBottomWidth: idx === CHANGELOG_HISTORY.length - 1 ? 0 : 1,
                  },
                ]}
              >
                <View style={styles.versionHeader}>
                  <Text style={[styles.versionName, { color: theme.colors.accent }]}>
                    {item.version}
                  </Text>
                  <Text style={[styles.versionDate, { color: theme.colors.textMuted }]}>
                    {item.date}
                  </Text>
                </View>

                <Text style={[styles.versionTitle, { color: theme.colors.heading }]}>
                  {item.title}
                </Text>

                {item.changes.map((change, cIdx) => (
                  <Text
                    key={cIdx}
                    style={[styles.changeItem, { color: theme.colors.text }]}
                  >
                    {change}
                  </Text>
                ))}
              </View>
            ))}
          </ScrollView>

          <Button
            title="Kapat"
            variant="secondary"
            onPress={handleClose}
            style={{ marginTop: 16 }}
          />
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  card: {
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderWidth: 1,
    padding: 24,
    paddingBottom: 40,
    maxHeight: '85%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  closeBtn: {
    padding: 6,
  },
  closeText: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  currentVersionBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 16,
    marginBottom: 16,
  },
  bannerTitle: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  bannerSub: {
    fontSize: 12,
    fontFamily: 'Inter',
    fontWeight: '600',
    marginTop: 2,
  },
  changelogScroll: {
    marginBottom: 8,
  },
  versionBlock: {
    paddingVertical: 14,
  },
  versionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  versionName: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  versionDate: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
  versionTitle: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 8,
  },
  changeItem: {
    fontSize: 13,
    fontFamily: 'Inter',
    lineHeight: 20,
    marginBottom: 4,
  },
});
