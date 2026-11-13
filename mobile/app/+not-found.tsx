import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';

/**
 * Bilinmeyen deep-link veya rota yakalayıcı (+not-found).
 * Kullanıcıya hiçbir koşulda Expo Router "Unmatched Route" ekranı göstermez;
 * doğrudan mevcut ana ekrana ('/') yönlendirir.
 */
export default function NotFoundRedirect() {
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
