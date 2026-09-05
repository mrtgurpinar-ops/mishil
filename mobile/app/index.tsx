import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../store/useAppStore';
import { storage } from '../lib/storage';

export default function Index() {
  const router = useRouter();
  const [isReady, setIsReady] = useState(false);
  const [hasBaby, setHasBaby] = useState(false);
  const activeBaby = useAppStore((state) => state.activeBaby);

  useEffect(() => {
    async function checkInitialState() {
      try {
        const storedBabyId = await storage.getActiveBabyId();
        if (activeBaby || storedBabyId) {
          setHasBaby(true);
        } else {
          setHasBaby(false);
        }
      } catch {
        setHasBaby(false);
      } finally {
        setIsReady(true);
      }
    }
    checkInitialState();
  }, [activeBaby]);

  useEffect(() => {
    if (isReady) {
      // Android FragmentManager race condition prevention:
      // Navigate safely via router.replace once the root window is attached
      const timer = setTimeout(() => {
        if (!hasBaby) {
          router.replace('/(onboarding)/baby-profile');
        } else {
          router.replace('/(tabs)/home');
        }
      }, 50);

      return () => clearTimeout(timer);
    }
  }, [isReady, hasBaby]);

  return (
    <View style={{ flex: 1, backgroundColor: '#141B2E', justifyContent: 'center', alignItems: 'center' }}>
      <ActivityIndicator size="large" color="#E8A855" />
      <Text style={{ marginTop: 16, color: '#C9CEDC', fontSize: 13, letterSpacing: 0.5, fontWeight: '500' }}>
        Mışıl Baby Yükleniyor...
      </Text>
    </View>
  );
}

