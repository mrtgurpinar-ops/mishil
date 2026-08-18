import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { BreathingMoonIndicator } from '../../components/BreathingMoonIndicator';

export default function MoonPreviewScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const [minutes, setMinutes] = useState(15);
  const [isSleeping, setIsSleeping] = useState(false);
  const [size, setSize] = useState(240);

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={[styles.backText, { color: theme.colors.accent }]}>
            ← Geri Dön
          </Text>
        </TouchableOpacity>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          İmza Hilal Göstergesi (Preview)
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          Reanimated ile 4 saniyelik nefes alma/verme ritmi, uyku yaklaşma uyarısı ve dinamik aura geçişleri.
        </Text>
      </View>

      {/* The Breathing Moon in Isolated Sandbox */}
      <View style={styles.stage}>
        <BreathingMoonIndicator
          minutesLeft={minutes}
          isSleeping={isSleeping}
          size={size}
          label={
            isSleeping
              ? '🌙 Bebek Derin Uykuda'
              : minutes <= 30
              ? `⚠️ ${minutes} dk Kaldı (Sıcak Bal Aurası)`
              : `💤 ${minutes} dk Kaldı (Sakin Gece Mavisi)`
          }
        />
      </View>

      {/* Interactive Controls */}
      <Card style={styles.controlsCard}>
        <Text style={[styles.controlSectionTitle, { color: theme.colors.heading }]}>
          Durum Simülasyonu
        </Text>

        <View style={styles.btnRow}>
          {[
            { label: '10 Dk (Acil/Sıcak)', val: 10, sleep: false },
            { label: '25 Dk (Yakın)', val: 25, sleep: false },
            { label: '60 Dk (Normal)', val: 60, sleep: false },
            { label: '120 Dk (Uzak)', val: 120, sleep: false },
            { label: 'Uykuda', val: 0, sleep: true },
          ].map((item, idx) => {
            const active = item.sleep === isSleeping && (item.sleep || item.val === minutes);
            return (
              <TouchableOpacity
                key={idx}
                onPress={() => {
                  setMinutes(item.val);
                  setIsSleeping(item.sleep);
                }}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active
                      ? theme.colors.accent
                      : theme.isDark
                      ? '#25304C'
                      : '#E5E0D8',
                  },
                ]}
              >
                <Text
                  style={[
                    styles.chipText,
                    {
                      color: active ? '#141B2E' : theme.colors.text,
                      fontWeight: active ? '700' : '400',
                    },
                  ]}
                >
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={[styles.controlSectionTitle, { color: theme.colors.heading, marginTop: 16 }]}>
          Boyut Seçimi
        </Text>
        <View style={styles.btnRow}>
          {[160, 220, 280].map((s) => (
            <TouchableOpacity
              key={s}
              onPress={() => setSize(s)}
              style={[
                styles.chip,
                {
                  backgroundColor: size === s
                    ? theme.colors.accent
                    : theme.isDark
                    ? '#25304C'
                    : '#E5E0D8',
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  {
                    color: size === s ? '#141B2E' : theme.colors.text,
                    fontWeight: size === s ? '700' : '400',
                  },
                ]}
              >
                {s}px
              </Text>
            </TouchableOpacity>
          ))}
        </View>
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
  backBtn: {
    marginBottom: 8,
  },
  backText: {
    fontSize: 14,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  title: {
    fontSize: 22,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    lineHeight: 18,
  },
  stage: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 24,
  },
  controlsCard: {
    padding: 20,
    marginTop: 8,
  },
  controlSectionTitle: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 10,
  },
  btnRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
  },
  chipText: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
});
