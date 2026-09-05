import React, { useState, useEffect } from 'react';
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
import { purchasePackage, getOfferings, restorePurchases, PackageOffer, FALLBACK_OFFERINGS } from '../../features/subscription/revenuecat';
import { useSubscriptionStatus } from '../../features/subscription/hooks/useSubscriptionStatus';

export default function SubscriptionScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const { startTrial } = useSubscriptionStatus();

  const [offerings, setOfferings] = useState<PackageOffer[]>(FALLBACK_OFFERINGS);
  const [selectedPlan, setSelectedPlan] = useState<string>('misil');
  const [loading, setLoading] = useState(false);
  const [loadingOfferings, setLoadingOfferings] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function loadDynamicOfferings() {
      try {
        const livePackages = await getOfferings();
        if (isMounted && livePackages && livePackages.length > 0) {
          setOfferings(livePackages);
          setSelectedPlan(livePackages[0].identifier);
        }
      } catch (err) {
        console.log('[Paywall] Offering fetch error:', err);
      } finally {
        if (isMounted) setLoadingOfferings(false);
      }
    }
    loadDynamicOfferings();
    return () => { isMounted = false; };
  }, []);

  const handlePurchase = async () => {
    try {
      setLoading(true);
      const chosenOffer = offerings.find((o) => o.identifier === selectedPlan);
      const res = await purchasePackage(selectedPlan, chosenOffer?.rawPackage);
      if (res.success) {
        await startTrial();
        router.back();
      }
    } catch (e) {
      console.warn('Purchase error:', e);
      router.back();
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async () => {
    try {
      setLoading(true);
      const res = await restorePurchases();
      if (res.success) {
        await startTrial();
        router.back();
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      contentContainerStyle={styles.scroll}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.closeBtn}>
          <Text style={[styles.closeIcon, { color: theme.colors.textMuted }]}>
            ✕ Kapat
          </Text>
        </TouchableOpacity>

        <Text style={styles.badge}>Mishil Premium</Text>
        <Text style={[styles.title, { color: theme.colors.heading }]}>
          Bebeğinizin Tüm Uyku & Ağlama İpuçları Cebinizde
        </Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
          3 gün boyunca hiçbir ücret ödemeden deneyin. Memnun kalmazsanız dilediğiniz an tek tıkla iptal edin.
        </Text>
      </View>

      {/* Feature Bullets */}
      <Card style={styles.featuresCard}>
        {[
          { icon: '🌙', title: 'Dinamik Uyku Penceresi', desc: 'Aşırı yorgunluk ve gecikme alarmları' },
          { icon: '🎙️', title: 'Sınırsız Ağlama Analizi', desc: 'MFCC ve spektral frekans tespiti' },
          { icon: '🎧', title: '432Hz & Arka Plan Sesleri', desc: 'Ekran kapalıyken kesintisiz beyaz/pembe gürültü' },
          { icon: '📋', title: 'Sınırsız Rutin Takibi', desc: 'Offline modda da tam kayıt ve grafikler' },
        ].map((f, i) => (
          <View key={i} style={styles.featureRow}>
            <Text style={styles.featureIcon}>{f.icon}</Text>
            <View style={styles.featureTextWrap}>
              <Text style={[styles.featureTitle, { color: theme.colors.heading }]}>
                {f.title}
              </Text>
              <Text style={[styles.featureDesc, { color: theme.colors.textMuted }]}>
                {f.desc}
              </Text>
            </View>
          </View>
        ))}
      </Card>

      {/* Pricing Options */}
      <View style={styles.plansContainer}>
        {offerings.map((offer) => {
          const isSelected = selectedPlan === offer.identifier;
          return (
            <TouchableOpacity
              key={offer.identifier}
              onPress={() => setSelectedPlan(offer.identifier)}
              activeOpacity={0.85}
            >
              <Card
                style={[
                  styles.planCard,
                  isSelected && {
                    borderColor: theme.colors.accent,
                    borderWidth: 2,
                    backgroundColor: theme.isDark ? '#232E4C' : '#FFF9F2',
                  },
                ]}
              >
                {offer.packageType === 'ANNUAL' ? (
                  <View style={styles.bestValueBadge}>
                    <Text style={styles.bestValueText}>En Çok Tercih Edilen • 3 Gün Ücretsiz</Text>
                  </View>
                ) : null}

                <View style={styles.planRow}>
                  <View style={styles.planInfo}>
                    <Text style={[styles.planTitle, { color: theme.colors.heading }]}>
                      {offer.title}
                    </Text>
                    <Text style={[styles.planDesc, { color: theme.colors.textMuted }]}>
                      {offer.description}
                    </Text>
                  </View>
                  <Text
                    style={[
                      styles.planPrice,
                      { color: isSelected ? theme.colors.accent : theme.colors.heading },
                    ]}
                  >
                    {offer.priceString}
                  </Text>
                </View>
              </Card>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* CTA Button */}
      <Button
        title="3 Gün Ücretsiz Başla"
        onPress={handlePurchase}
        loading={loading}
        size="lg"
        style={styles.ctaBtn}
      />

      {/* Honest Transparency Terms */}
      <Text style={[styles.termsText, { color: theme.colors.textMuted }]}>
        3 günlük ücretsiz deneme süreniz sona ermeden 24 saat önce iptal ederseniz hiçbir ücret yansıtılmaz.
        Abonelik App Store / Google Play hesabınız üzerinden yönetilir ve otomatik yenilenir.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    padding: 24,
    paddingTop: 50,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 20,
  },
  closeBtn: {
    alignSelf: 'flex-start',
    marginBottom: 16,
  },
  closeIcon: {
    fontSize: 14,
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  badge: {
    fontSize: 12,
    color: '#E8A855',
    fontFamily: 'Inter',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 6,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 8,
    lineHeight: 30,
  },
  subtitle: {
    fontSize: 14,
    fontFamily: 'Inter',
    lineHeight: 20,
  },
  featuresCard: {
    padding: 18,
    marginBottom: 20,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 8,
  },
  featureIcon: {
    fontSize: 22,
    marginRight: 14,
  },
  featureTextWrap: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  featureDesc: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  plansContainer: {
    gap: 12,
    marginBottom: 20,
  },
  planCard: {
    padding: 16,
    position: 'relative',
  },
  bestValueBadge: {
    position: 'absolute',
    top: -10,
    left: 16,
    backgroundColor: '#E8A855',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  bestValueText: {
    color: '#141B2E',
    fontSize: 10,
    fontFamily: 'Inter',
    fontWeight: '700',
  },
  planRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  planInfo: {
    flex: 1,
    marginRight: 12,
  },
  planTitle: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  planDesc: {
    fontSize: 12,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  planPrice: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  ctaBtn: {
    marginVertical: 12,
  },
  termsText: {
    fontSize: 11,
    fontFamily: 'Inter',
    textAlign: 'center',
    lineHeight: 16,
    paddingHorizontal: 12,
  },
});
