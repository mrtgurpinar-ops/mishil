import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { CryResultCard, CryAnalysisResult } from '../../components/CryResultCard';
import { useCryRecorder } from '../../features/cry-analysis/hooks/useCryRecorder';
import { uploadAndAnalyzeCryAudio } from '../../features/cry-analysis/api';
import { useSubscriptionStatus } from '../../features/subscription/hooks/useSubscriptionStatus';
import { triggerHaptic } from '../../lib/haptics';

export default function CryAnalysisScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);
  const { isPremiumActive } = useSubscriptionStatus();

  const {
    isRecording,
    recordingSeconds,
    meteringLevel,
    startRecording,
    stopRecording,
    cancelRecording,
    maxSeconds,
  } = useCryRecorder();

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<CryAnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleStart = async () => {
    triggerHaptic('medium');
    setErrorMessage(null);
    setAnalysisResult(null);
    try {
      await startRecording();
    } catch (err: any) {
      setErrorMessage(err.message || 'Mikrofon başlatılamadı.');
      triggerHaptic('error');
    }
  };

  const handleStopAndAnalyze = async () => {
    triggerHaptic('medium');
    try {
      const uri = await stopRecording();
      if (!uri) {
        setErrorMessage('Kayıt dosyası bulunamadı.');
        return;
      }

      setIsAnalyzing(true);
      setUploadPercent(0);

      const result = await uploadAndAnalyzeCryAudio({
        audioUri: uri,
        babyId: activeBaby?.id,
        onProgress: (pct) => setUploadPercent(pct),
      });

      triggerHaptic('success');
      setAnalysisResult(result);
    } catch (err: any) {
      triggerHaptic('error');
      setErrorMessage(err.message || 'Analiz sırasında bir hata oluştu.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Ağlama Sesi Analizi
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          Bebeğinizin ağlama frekans ve ritmini kaydederek akustik yapay zeka ile değerlendirin.
        </Text>
      </View>

      {/* Recording Stage Card */}
      {!analysisResult ? (
        <Card style={styles.recorderCard}>
          {isRecording ? (
            <View style={styles.recordingState}>
              <View style={[styles.waveCircle, { transform: [{ scale: 1 + meteringLevel * 0.4 }] }]}>
                <View style={[styles.waveInner, { backgroundColor: theme.colors.accent }]} />
              </View>

              <Text style={[styles.timerText, { color: theme.colors.accent }]}>
                00:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 00:{maxSeconds}
              </Text>
              <Text style={[styles.recordingHint, { color: theme.colors.textMuted }]}>
                Bebeğinize yakın tutunuz...
              </Text>

              <View style={styles.buttonRow}>
                <Button
                  title="Kaydı Bitir ve Analiz Et"
                  onPress={handleStopAndAnalyze}
                  style={styles.stopBtn}
                />
                <Button
                  title="İptal"
                  variant="ghost"
                  onPress={() => {
                    triggerHaptic('light');
                    cancelRecording();
                  }}
                />
              </View>
            </View>
          ) : isAnalyzing ? (
            <View style={styles.analyzingState}>
              <ActivityIndicator color={theme.colors.accent} size="large" />
              <Text style={[styles.analyzingTitle, { color: theme.colors.heading }]}>
                Akustik Spektrum İnceleniyor...
              </Text>
              <Text style={[styles.analyzingSubtitle, { color: theme.colors.textMuted }]}>
                13-Band MFCC öznitelikleri ve spektral enerji hesaplanıyor (%{uploadPercent})
              </Text>
              <ProgressBar progress={uploadPercent} style={styles.uploadProgress} />
            </View>
          ) : (
            <View style={styles.idleState}>
              <TouchableOpacity
                onPress={handleStart}
                style={[
                  styles.micButton,
                  {
                    backgroundColor: theme.colors.accent,
                    shadowColor: theme.colors.accent,
                  },
                ]}
                accessibilityLabel="Ses kaydını başlat"
                activeOpacity={0.8}
              >
                <Text style={styles.micIcon}>🎙️</Text>
              </TouchableOpacity>

              <Text style={[styles.idleTitle, { color: theme.colors.heading }]}>
                Kaydı Başlatmak İçin Dokunun
              </Text>
              <Text style={[styles.idleSubtitle, { color: theme.colors.textMuted }]}>
                En iyi sonuç için 10-30 saniye arası net bir ağlama kaydı gereklidir.
              </Text>
            </View>
          )}

          {errorMessage ? (
            <Text style={[styles.errorText, { color: theme.colors.error }]}>
              {errorMessage}
            </Text>
          ) : null}
        </Card>
      ) : null}

      {/* Analysis Result Presentation */}
      {analysisResult ? (
        <View>
          <CryResultCard
            result={analysisResult}
            onPlayRecommendedSound={() => {
              triggerHaptic('light');
              router.push('/(tabs)/sounds');
            }}
          />

          <Button
            title="Yeni Kayıt Al"
            variant="secondary"
            onPress={() => {
              triggerHaptic('light');
              setAnalysisResult(null);
              setErrorMessage(null);
            }}
            style={styles.newRecordBtn}
          />
        </View>
      ) : null}
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
    marginBottom: 20,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 14,
    fontFamily: 'Inter',
    lineHeight: 20,
  },
  recorderCard: {
    alignItems: 'center',
    padding: 28,
    marginVertical: 12,
    borderRadius: 24,
  },
  idleState: {
    alignItems: 'center',
  },
  micButton: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 8,
  },
  micIcon: {
    fontSize: 40,
  },
  idleTitle: {
    fontSize: 17,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 6,
  },
  idleSubtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    textAlign: 'center',
    lineHeight: 18,
    paddingHorizontal: 12,
  },
  recordingState: {
    alignItems: 'center',
    width: '100%',
  },
  waveCircle: {
    width: 84,
    height: 84,
    borderRadius: 42,
    backgroundColor: 'rgba(232, 168, 85, 0.2)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  waveInner: {
    width: 34,
    height: 34,
    borderRadius: 17,
  },
  timerText: {
    fontSize: 22,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 4,
  },
  recordingHint: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginBottom: 20,
  },
  buttonRow: {
    width: '100%',
    gap: 8,
  },
  stopBtn: {
    width: '100%',
  },
  analyzingState: {
    alignItems: 'center',
    paddingVertical: 20,
    width: '100%',
  },
  analyzingTitle: {
    fontSize: 16,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginTop: 16,
    marginBottom: 4,
  },
  analyzingSubtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    textAlign: 'center',
    marginBottom: 16,
  },
  uploadProgress: {
    width: '80%',
  },
  errorText: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 14,
    textAlign: 'center',
  },
  newRecordBtn: {
    marginTop: 8,
    marginBottom: 20,
  },
});
