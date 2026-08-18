import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { SoundPlayerBar, SoundTrack } from '../../components/SoundPlayerBar';

const SOUNDS_DATA: SoundTrack[] = [
  {
    id: 'snd_pink_432',
    title: '432Hz Derin Pembe Gürültü',
    category: 'Gürültü Frekansları',
    streamUrl: 'https://cdn.mishil.app/audio/pink_noise_432hz.mp3',
  },
  {
    id: 'snd_womb',
    title: 'Anne Karnı & Kalp Atışı',
    category: 'Rahatlatıcı Ortam',
    streamUrl: 'https://cdn.mishil.app/audio/womb_sounds.mp3',
  },
  {
    id: 'snd_shushing',
    title: 'Ritmik Pışpışlama (5S)',
    category: 'Sakinleştirici',
    streamUrl: 'https://cdn.mishil.app/audio/shushing_rhythmic.mp3',
  },
  {
    id: 'snd_white_noise',
    title: 'Klasik Beyaz Gürültü',
    category: 'Gürültü Frekansları',
    streamUrl: 'https://cdn.mishil.app/audio/white_noise.mp3',
  },
  {
    id: 'snd_rain',
    title: 'Hafif Yağmur & Doğa',
    category: 'Doğa Sesleri',
    streamUrl: 'https://cdn.mishil.app/audio/rain_gentle.mp3',
  },
  {
    id: 'snd_lullaby',
    title: 'Brahms Ninni (Müzik Kutusu)',
    category: 'Ninniler',
    streamUrl: 'https://cdn.mishil.app/audio/brahms_lullaby.mp3',
  },
];

export default function SoundsScreen() {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const [activeTrack, setActiveTrack] = useState<SoundTrack | null>(SOUNDS_DATA[0]);

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.background }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Sakinleştirici Sesler
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          Bebeğinizi derin uykuya hazırlayan bilimsel frekanslar ve ortam sesleri (Arka planda kesintisiz çalar).
        </Text>
      </View>

      <FlatList
        data={SOUNDS_DATA}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => {
          const isPlaying = activeTrack?.id === item.id;
          return (
            <TouchableOpacity
              onPress={() => setActiveTrack(item)}
              activeOpacity={0.8}
            >
              <Card
                style={[
                  styles.soundCard,
                  isPlaying && { borderColor: theme.colors.accent, borderWidth: 1.5 },
                ]}
              >
                <View style={styles.cardRow}>
                  <View
                    style={[
                      styles.iconWrap,
                      {
                        backgroundColor: isPlaying
                          ? theme.colors.accent
                          : theme.isDark
                          ? '#25304C'
                          : '#E8EDF5',
                      },
                    ]}
                  >
                    <Text style={{ fontSize: 20 }}>
                      {item.id.includes('pink')
                        ? '🌸'
                        : item.id.includes('womb')
                        ? '❤️'
                        : item.id.includes('shushing')
                        ? '🤫'
                        : item.id.includes('rain')
                        ? '🌧️'
                        : '🎵'}
                    </Text>
                  </View>

                  <View style={styles.textWrap}>
                    <Text
                      style={[
                        styles.soundTitle,
                        {
                          color: isPlaying ? theme.colors.accent : theme.colors.heading,
                        },
                      ]}
                    >
                      {item.title}
                    </Text>
                    <Text style={[styles.category, { color: theme.colors.textMuted }]}>
                      {item.category}
                    </Text>
                  </View>

                  <Text
                    style={[
                      styles.playBtnIcon,
                      { color: isPlaying ? theme.colors.accent : theme.colors.textMuted },
                    ]}
                  >
                    {isPlaying ? '▶ Çalıyor' : 'Çal'}
                  </Text>
                </View>
              </Card>
            </TouchableOpacity>
          );
        }}
      />

      <SoundPlayerBar
        currentTrack={activeTrack}
        onClose={() => setActiveTrack(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 56,
    paddingBottom: 16,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    lineHeight: 18,
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 140,
  },
  soundCard: {
    marginVertical: 6,
    padding: 14,
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  textWrap: {
    flex: 1,
  },
  soundTitle: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  category: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  playBtnIcon: {
    fontSize: 13,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
});
