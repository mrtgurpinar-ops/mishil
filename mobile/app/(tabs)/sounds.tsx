import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { SoundPlayerBar, SoundTrack } from '../../components/SoundPlayerBar';
import { triggerHaptic } from '../../lib/haptics';

const BASE_AUDIO_URL = 'https://mishil-api-production.up.railway.app/sounds';

const SOUNDS_DATA: SoundTrack[] = [
  // 1. Ninniler (Lullabies)
  {
    id: 'brahms_lullaby',
    title: 'Brahms Uyku Ninnisi',
    category: 'Ninniler',
    streamUrl: `${BASE_AUDIO_URL}/brahms_lullaby.mp3`,
  },
  {
    id: 'moonlight_lullaby',
    title: 'Ayışığı Piyano Melodisi',
    category: 'Ninniler',
    streamUrl: `${BASE_AUDIO_URL}/moonlight_lullaby.mp3`,
  },
  {
    id: 'mozart_432hz',
    title: 'Mozart Zeka Gelişim Ninnisi (432Hz)',
    category: 'Ninniler',
    streamUrl: `${BASE_AUDIO_URL}/mozart_432hz.mp3`,
  },
  {
    id: 'music_box_celesta',
    title: 'Müzik Kutusu Rüzgar Çanları',
    category: 'Ninniler',
    streamUrl: `${BASE_AUDIO_URL}/music_box_celesta.mp3`,
  },
  {
    id: 'velvet_guitar',
    title: 'Kadife Gece Gitarı',
    category: 'Ninniler',
    streamUrl: `${BASE_AUDIO_URL}/velvet_guitar.mp3`,
  },

  // 2. Anne Karnı (Womb)
  {
    id: 'deep_heartbeat',
    title: 'Tok Anne Kalp Atışı (Lub-Dub)',
    category: 'Anne Karnı',
    streamUrl: `${BASE_AUDIO_URL}/deep_heartbeat.mp3`,
  },
  {
    id: 'womb_amniotic',
    title: 'Amniyotik Sıvı & Anne Karnı',
    category: 'Anne Karnı',
    streamUrl: `${BASE_AUDIO_URL}/womb_amniotic.mp3`,
  },
  {
    id: 'placenta_flow',
    title: 'Plasenta & Ritmik Akış',
    category: 'Anne Karnı',
    streamUrl: `${BASE_AUDIO_URL}/placenta_flow.mp3`,
  },
  {
    id: 'calm_breath',
    title: 'Anne Göğsü & Sakin Ritim',
    category: 'Anne Karnı',
    streamUrl: `${BASE_AUDIO_URL}/calm_breath.mp3`,
  },

  // 3. Pışpış & Frekanslar (Shush & Noise)
  {
    id: 'shush_5s',
    title: '5S Dr. Karp Doğal Pışpış',
    category: 'Pışpış & Gürültü',
    streamUrl: `${BASE_AUDIO_URL}/shush_5s.mp3`,
  },
  {
    id: 'pink_432hz',
    title: '432Hz Derin Pembe Gürültü',
    category: 'Pışpış & Gürültü',
    streamUrl: `${BASE_AUDIO_URL}/pink_432hz.mp3`,
  },
  {
    id: 'brown_noise_colic',
    title: 'Kadife Kahverengi Kolik Kalkanı',
    category: 'Pışpış & Gürültü',
    streamUrl: `${BASE_AUDIO_URL}/brown_noise_colic.mp3`,
  },
  {
    id: 'hairdryer_calm',
    title: 'İpeksi Fön Makinesi Sesi',
    category: 'Pışpış & Gürültü',
    streamUrl: `${BASE_AUDIO_URL}/hairdryer_calm.mp3`,
  },
  {
    id: 'fan_drone',
    title: 'Oda Vantilatörü & Ritmik Dron',
    category: 'Pışpış & Gürültü',
    streamUrl: `${BASE_AUDIO_URL}/fan_drone.mp3`,
  },

  // 4. Doğa Sesleri (Nature)
  {
    id: 'forest_stream',
    title: 'Orman Deresi & Kuşlar',
    category: 'Doğa Sesleri',
    streamUrl: `${BASE_AUDIO_URL}/forest_stream.mp3`,
  },
  {
    id: 'soft_rain',
    title: 'Pencereye Vuran Gece Yağmuru',
    category: 'Doğa Sesleri',
    streamUrl: `${BASE_AUDIO_URL}/soft_rain.mp3`,
  },
  {
    id: 'ocean_calm',
    title: 'Kumsala Vuran Gece Okyanusu',
    category: 'Doğa Sesleri',
    streamUrl: `${BASE_AUDIO_URL}/ocean_calm.mp3`,
  },
  {
    id: 'night_crickets',
    title: 'Yaz Gecesi Cırcır Böcekleri',
    category: 'Doğa Sesleri',
    streamUrl: `${BASE_AUDIO_URL}/night_crickets.mp3`,
  },
];

const CATEGORIES = ['Tümü', 'Ninniler', 'Anne Karnı', 'Pışpış & Gürültü', 'Doğa Sesleri'];

export default function SoundsScreen() {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const [activeTrack, setActiveTrack] = useState<SoundTrack | null>(null);
  const [selectedCategory, setSelectedCategory] = useState('Tümü');

  const filteredSounds = SOUNDS_DATA.filter((sound) =>
    selectedCategory === 'Tümü' ? true : sound.category === selectedCategory
  );


  return (
    <View style={[styles.container, { backgroundColor: theme.colors.background }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Sakinleştirici Sesler
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          Bebeğinizi derin uykuya hazırlayan bilimsel 18 stüdyo frekansı ve ortam sesi (Arka planda kesintisiz çalar).
        </Text>

        {/* Kategori Filtreleri */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.categoryScroll}
        >
          {CATEGORIES.map((cat) => {
            const isSelected = selectedCategory === cat;
            return (
              <TouchableOpacity
                key={cat}
                onPress={() => {
                  triggerHaptic('selection');
                  setSelectedCategory(cat);
                }}
                style={[
                  styles.catChip,
                  {
                    backgroundColor: isSelected
                      ? theme.colors.accent
                      : theme.isDark
                      ? '#1F2942'
                      : '#E8EDF5',
                  },
                ]}
              >
                <Text
                  style={[
                    styles.catChipText,
                    {
                      color: isSelected ? '#141B2E' : theme.colors.text,
                      fontWeight: isSelected ? '700' : '500',
                    },
                  ]}
                >
                  {cat}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      <FlatList
        data={filteredSounds}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => {
          const isPlaying = activeTrack?.id === item.id;
          return (
            <TouchableOpacity
              onPress={() => {
                triggerHaptic('light');
                setActiveTrack(item);
              }}
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
    marginBottom: 12,
  },
  categoryScroll: {
    paddingVertical: 6,
    gap: 8,
  },
  catChip: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 16,
    marginRight: 6,
  },
  catChipText: {
    fontSize: 12,
    fontFamily: 'Inter',
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
