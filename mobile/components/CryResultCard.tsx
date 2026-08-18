import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';
import { Card } from './ui/Card';
import { ProgressBar } from './ui/ProgressBar';
import { Button } from './ui/Button';

export interface CryCauseItem {
  cause: string;
  cause_title: string;
  likelihood: number;
  description: string;
}

export interface CryAnalysisResult {
  audio_duration_seconds: number;
  possible_causes: CryCauseItem[];
  dominant_cause: string;
  confidence_note: string;
  recommended_action: string;
  recommended_sound_type: string;
  sound_url_mock: string;
}

interface CryResultCardProps {
  result: CryAnalysisResult;
  onPlayRecommendedSound?: (soundType: string) => void;
}

export const CryResultCard: React.FC<CryResultCardProps> = ({
  result,
  onPlayRecommendedSound,
}) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  return (
    <View style={styles.container}>
      {/* 1. Mandatory Clinical Confidence Disclaimer Banner (Prominent & Clear) */}
      <View
        style={[
          styles.disclaimerBox,
          {
            backgroundColor: theme.isDark ? '#2D241E' : '#FFF5EB',
            borderColor: theme.colors.accent,
          },
        ]}
      >
        <Text style={[styles.disclaimerIcon]}>ℹ️</Text>
        <Text
          style={[
            styles.disclaimerText,
            { color: theme.isDark ? '#F5C68A' : '#8A4F1D' },
          ]}
        >
          {result.confidence_note ||
            'Bu analiz bir klinik veya tıbbi tanı değildir; ebeveynlere yönelik rehberlik ipucu niteliğindedir.'}
        </Text>
      </View>

      {/* 2. Probability Distribution Card */}
      <Card style={styles.card}>
        <Text style={[styles.sectionTitle, { color: theme.colors.heading }]}>
          Olasılık Dağılımı
        </Text>
        <Text style={[styles.sectionSubtitle, { color: theme.colors.textMuted }]}>
          Akustik frekans ve ritim özniteliklerine göre tahmin edilen nedenler:
        </Text>

        <View style={styles.causesList}>
          {result.possible_causes.map((item, index) => {
            const percentage = Math.round(item.likelihood * 100);
            const isDominant = index === 0;

            return (
              <View key={item.cause} style={styles.causeRow}>
                <View style={styles.causeHeader}>
                  <Text
                    style={[
                      styles.causeTitle,
                      {
                        color: isDominant
                          ? theme.colors.accent
                          : theme.colors.heading,
                        fontWeight: isDominant ? '700' : '500',
                      },
                    ]}
                  >
                    {item.cause_title}
                  </Text>
                  <Text
                    style={[
                      styles.causePercentage,
                      {
                        color: isDominant
                          ? theme.colors.accent
                          : theme.colors.textMuted,
                      },
                    ]}
                  >
                    %{percentage}
                  </Text>
                </View>

                <ProgressBar
                  progress={percentage}
                  color={isDominant ? theme.colors.accent : theme.colors.moonBlue}
                  height={8}
                  style={styles.progressBar}
                />

                <Text
                  style={[styles.causeDesc, { color: theme.colors.textMuted }]}
                >
                  {item.description}
                </Text>
              </View>
            );
          })}
        </View>
      </Card>

      {/* 3. Recommended Action & Soothing Sound */}
      <Card style={[styles.card, { borderColor: theme.colors.accent, borderWidth: 1.2 }]}>
        <Text style={[styles.sectionTitle, { color: theme.colors.accent }]}>
          Önerilen Ebeveyn Aksiyonu
        </Text>
        <Text style={[styles.actionText, { color: theme.colors.heading }]}>
          {result.recommended_action}
        </Text>

        {result.recommended_sound_type ? (
          <View style={styles.soundActionContainer}>
            <View style={styles.soundInfo}>
              <Text style={[styles.soundLabel, { color: theme.colors.textMuted }]}>
                Önerilen Sakinleştirici Ses:
              </Text>
              <Text style={[styles.soundValue, { color: theme.colors.heading }]}>
                {result.recommended_sound_type.replace(/_/g, ' ').toUpperCase()}
              </Text>
            </View>
            <Button
              title="Sesi Başlat"
              size="sm"
              onPress={() =>
                onPlayRecommendedSound?.(result.recommended_sound_type)
              }
            />
          </View>
        ) : null}
      </Card>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 12,
  },
  disclaimerBox: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    marginBottom: 16,
  },
  disclaimerIcon: {
    fontSize: 18,
    marginRight: 10,
  },
  disclaimerText: {
    flex: 1,
    fontSize: 13,
    fontFamily: 'Inter',
    fontWeight: '500',
    lineHeight: 18,
  },
  card: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 17,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginBottom: 16,
  },
  causesList: {
    gap: 16,
  },
  causeRow: {
    marginBottom: 6,
  },
  causeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  causeTitle: {
    fontSize: 15,
    fontFamily: 'Inter',
  },
  causePercentage: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  progressBar: {
    marginVertical: 4,
  },
  causeDesc: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 4,
  },
  actionText: {
    fontSize: 15,
    fontFamily: 'Inter',
    lineHeight: 22,
    marginTop: 6,
    marginBottom: 14,
  },
  soundActionContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.08)',
  },
  soundInfo: {
    flex: 1,
    marginRight: 12,
  },
  soundLabel: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
  soundValue: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginTop: 2,
  },
});
