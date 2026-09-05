import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Redirect } from 'expo-router';
import { useAppStore } from '../store/useAppStore';
import { storage } from '../lib/storage';

export default function Index() {
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

  if (!isReady) {
    return (
      <View style={{ flex: 1, backgroundColor: '#141B2E', justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color="#E8A855" />
      </View>
    );
  }

  if (!hasBaby) {
    return <Redirect href="/(onboarding)/baby-profile" />;
  }

  return <Redirect href="/(tabs)/home" />;
}

