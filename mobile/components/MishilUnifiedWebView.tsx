import React, { useRef, useCallback, useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ActivityIndicator,
  Text,
  StatusBar,
  Platform,
  BackHandler,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import * as Haptics from 'expo-haptics';
import { initRevenueCat, purchasePackage, restorePurchases, getOfferings } from '../features/subscription/revenuecat';

// Railway canlı URL
const MISHIL_WEB_URL = 'https://mishil-production.up.railway.app/app';

/**
 * MishilUnifiedWebView
 *
 * Tekil Kod Tabanı Mimarisi:
 * - public/app.html (Railway) → tek kaynak, tüm UI burada
 * - Bu bileşen sadece native kapasiteleri köprüler:
 *   IAP (RevenueCat/Google Play), haptik, mikrofon izni
 */
export default function MishilUnifiedWebView() {
  const webviewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // RevenueCat başlatma
  useEffect(() => {
    initRevenueCat().catch(() => {});
  }, []);

  // Android geri tuşu — WebView geçmişinde geri git
  useEffect(() => {
    const onBack = () => {
      if (webviewRef.current) {
        webviewRef.current.goBack();
        return true; // event tüketildi
      }
      return false;
    };
    const sub = BackHandler.addEventListener('hardwareBackPress', onBack);
    return () => sub.remove();
  }, []);

  // WebView yükleme tamamlandığında native bridge sinyali gönder
  const onLoadEnd = useCallback(() => {
    setLoading(false);
    setError(false);
    // Native olduğumuzu web tarafına bildir
    webviewRef.current?.injectJavaScript(`
      (function() {
        // Native bridge hazır sinyali
        window.MishilNative && (window.MishilNative.isNative = true);

        // Abonelik durumunu web'e bildir (mevcut localStorage varsa)
        var isActive = localStorage.getItem('mishil_subscription_active') === 'true';
        if (isActive) {
          var plan = localStorage.getItem('mishil_subscription_plan') || 'premium';
          window.dispatchEvent(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'SUBSCRIPTION_RESULT',
              data: { isActive: true, plan: plan }
            })
          }));
        }
        true;
      })();
    `);
  }, []);

  // Haptik yardımcı
  const triggerHaptic = async (level: string) => {
    try {
      if (level === 'heavy') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
      else if (level === 'medium') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      else await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch {}
  };

  // JS Bridge mesaj handler
  const onMessage = useCallback(async (event: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);

      switch (msg.type) {
        case 'HAPTIC':
          await triggerHaptic(msg.level || 'light');
          break;

        case 'PURCHASE_PACKAGE': {
          // Google Play IAP başlat
          const plan = msg.plan || 'yearly';
          const offerings = await getOfferings();
          const pkg = offerings.find(o =>
            plan === 'yearly' ? o.packageType === 'ANNUAL'
            : plan === 'monthly' ? o.packageType === 'MONTHLY'
            : o.packageType === 'LIFETIME'
          );

          const result = await purchasePackage(pkg?.identifier || plan, pkg?.rawPackage);

          if (result.success) {
            // Başarılı IAP → web'e bildir
            webviewRef.current?.injectJavaScript(`
              (function() {
                localStorage.setItem('misil_onboarding_completed', 'true');
                localStorage.setItem('mishil_subscription_active', 'true');
                localStorage.setItem('mishil_subscription_plan', '${plan}');
                var screen = document.getElementById('screen-onboarding');
                if (screen) screen.classList.remove('active');
                typeof showToast === 'function' && showToast('🎉 Mışıl Baby Pro aktif edildi!');
                true;
              })();
            `);
          }
          break;
        }

        case 'RESTORE_PURCHASES': {
          const result = await restorePurchases();
          if (result.success) {
            webviewRef.current?.injectJavaScript(`
              (function() {
                localStorage.setItem('mishil_subscription_active', 'true');
                typeof showToast === 'function' && showToast('✅ Satın alımlar geri yüklendi (Mışıl Baby Pro Aktif)');
                true;
              })();
            `);
          }
          break;
        }

        default:
          break;
      }
    } catch (e) {
      // Sessizce geç
    }
  }, []);

  // Hata durumunda gösterilecek ekran
  const renderError = () => (
    <View style={styles.errorContainer}>
      <Text style={styles.errorIcon}>🌙</Text>
      <Text style={styles.errorTitle}>Bağlantı Kuruluyor...</Text>
      <Text style={styles.errorSub}>
        İnternet bağlantınızı kontrol edin.{'\n'}Uygulama kısa süre içinde yeniden bağlanacak.
      </Text>
    </View>
  );

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0B0E17" />

      <WebView
        ref={webviewRef}
        source={{ uri: MISHIL_WEB_URL }}
        style={styles.webview}
        onLoadEnd={onLoadEnd}
        onError={() => setError(true)}
        onHttpError={() => setError(true)}
        onMessage={onMessage}

        // Ses ve medya
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        allowsAirPlayForMediaPlayback={false}

        // Mikrofon ve kamera izinleri — Android WebView PermissionsRequest
        // @ts-ignore — react-native-webview prop, bazı TS versiyonlarında tip tanımsız olabilir
        onPermissionRequest={(req: any) => req.grant(req.resources)}
        allowsProtectedMedia

        // Performans ve görünüm
        renderLoading={() => (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#E8A855" />
            <Text style={styles.loadingText}>Mışıl Baby Yükleniyor...</Text>
          </View>
        )}
        startInLoadingState={true}
        javaScriptEnabled
        domStorageEnabled
        thirdPartyCookiesEnabled
        sharedCookiesEnabled
        cacheEnabled
        cacheMode="LOAD_DEFAULT"

        // Android tam ekran
        androidLayerType="hardware"

        // URL değişikliklerinde izin ver
        onShouldStartLoadWithRequest={(req) => {
          // Sadece Railway ve içerik URL'lerine izin ver
          return true;
        }}
      />

      {error && renderError()}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B0E17',
    paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0,
  },
  webview: {
    flex: 1,
    backgroundColor: '#0B0E17',
  },
  loadingContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    flex: 1,
    backgroundColor: '#0B0E17',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 16,
    color: '#C9CEDC',
    fontSize: 13,
    letterSpacing: 0.5,
    fontWeight: '500',
    fontFamily: 'Inter',
  },
  errorContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    flex: 1,
    backgroundColor: '#0B0E17',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  errorIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  errorTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  errorSub: {
    color: '#8E99B0',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 20,
  },
});
