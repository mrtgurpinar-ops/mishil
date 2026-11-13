import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';

/**
 * misilbaby://sleep için ek güvenlik rotası.
 * Normal akışta +native-intent.tsx doğrudan '/' rotasına çevirir;
 * herhangi bir doğrudan navigasyonda siyah hata ekranı yerine mevcut ana ekrana döner.
 */
export default function SleepDeepLinkFallback() {
  const router = useRouter();

  useEffect(() => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/');
    }
  }, [router]);

  return <View style={styles.bg} />;
}

const styles = StyleSheet.create({
  bg: {
    flex: 1,
    backgroundColor: '#0B0E17',
  },
});
