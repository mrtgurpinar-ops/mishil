import React, { useRef, useCallback, useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ActivityIndicator,
  Text,
  Pressable,
  StatusBar,
  Platform,
  BackHandler,
  AppState,
  AppStateStatus,
  Linking,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import * as Haptics from 'expo-haptics';
import Constants from 'expo-constants';
import { initRevenueCat, purchasePackage, restorePurchases, getOfferings, hasActiveEntitlement, PRO_ENTITLEMENT_ID } from '../features/subscription/revenuecat';
import * as nativeAudio from '../features/audio/nativeAudioPlayer';
import { OFFLINE_HTML } from '../features/webview/offlineHtml.generated';

// Railway canlı URL
const MISHIL_WEB_ORIGIN = 'https://mishil-production.up.railway.app';
const MISHIL_WEB_URL = `${MISHIL_WEB_ORIGIN}/app`;

// Native sürüm bilgisini WebView'e sayfa yüklenmeden önce enjekte et (Settings sürüm rozeti + changelog dinamik)
const APP_VERSION = Constants.expoConfig?.version ?? '0.0.0';
const APP_BUILD =
  Platform.OS === 'ios'
    ? (Constants.expoConfig?.ios?.buildNumber ?? '0')
    : String(Constants.expoConfig?.android?.versionCode ?? '0');
const INJECT_APP_META = `
  window.__MISHIL_APP__ = { version: ${JSON.stringify(APP_VERSION)}, build: ${JSON.stringify(APP_BUILD)}, platform: ${JSON.stringify(Platform.OS)}, native: true };
  window.MishilNative = window.MishilNative || {};
  window.MishilNative.isNative = true;
  window.MishilNative.audioBridge = true;
  true;
`;

// Sayfa bu süre içinde yüklenmezse (Railway cold-start / zayıf şebeke) hata ekranına düş
const LOAD_TIMEOUT_MS = 25000;
// Kullanıcı dokunmadan sessizce kaç kez yeniden denensin (cold-start toleransı)
const MAX_AUTO_RETRY = 3;
// Çevrimdışı moddayken uzak sürüme yeniden bağlanma denemesi aralığı
const RECONNECT_PROBE_MS = 20000;
// Gömülü çevrimdışı sürüm kullanılabilir mi (EAS'te kaynak yoksa boş kalabilir)
const HAS_OFFLINE_HTML = typeof OFFLINE_HTML === 'string' && OFFLINE_HTML.length > 500;

type Status = 'loading' | 'ready' | 'error';

/**
 * MishilUnifiedWebView
 *
 * Tekil Kod Tabanı Mimarisi:
 * - public/app.html (Railway) → tek kaynak, tüm UI burada
 * - Bu bileşen sadece native kapasiteleri köprüler:
 *   IAP (RevenueCat/Google Play), haptik, mikrofon izni
 *
 * Dayanıklılık: uygulama %100 uzak URL'e bağımlı olduğu için WebView render
 * sürecinin çökmesi, TLS/şebeke hatası veya Railway soğuk başlangıcı durumunda
 * kullanıcıyı boş/siyah ekranda bırakmadan otomatik + manuel yeniden deneme sağlar.
 */
export default function MishilUnifiedWebView() {
  const webviewRef = useRef<WebView>(null);
  const [status, setStatus] = useState<Status>('loading');
  // Uzak sürüm tekrar tekrar başarısız olduğunda gömülü app.html'e düşülür
  const [useOffline, setUseOffline] = useState(false);
  const retryCountRef = useRef(0);
  const autoRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimers = () => {
    if (autoRetryTimer.current) { clearTimeout(autoRetryTimer.current); autoRetryTimer.current = null; }
    if (watchdogTimer.current) { clearTimeout(watchdogTimer.current); watchdogTimer.current = null; }
  };

  const stopReconnectProbe = () => {
    if (reconnectTimer.current) { clearInterval(reconnectTimer.current); reconnectTimer.current = null; }
  };

  // RevenueCat başlatma + native ses motoru temizliği
  useEffect(() => {
    initRevenueCat().catch(() => {});
    return () => {
      clearTimers();
      stopReconnectProbe();
      void nativeAudio.shutdown();
    };
  }, []);

  // Çevrimdışı moddayken uzak sürüme sessizce yeniden bağlanmayı dener.
  // Başarılıysa source {uri}'ye döner; onLoadStart watchdog'u yeniden kurar.
  const startReconnectProbe = useCallback(() => {
    stopReconnectProbe();
    reconnectTimer.current = setInterval(async () => {
      try {
        const res = await fetch(MISHIL_WEB_URL, { method: 'HEAD', cache: 'no-store' as RequestCache });
        if (res && res.ok) {
          stopReconnectProbe();
          retryCountRef.current = 0;
          setStatus('loading');
          setUseOffline(false);
        }
      } catch {
        // hâlâ erişilemiyor — bir sonraki denemeyi bekle
      }
    }, RECONNECT_PROBE_MS);
  }, []);

  // Native ses durumunu web'e bildir (mini player UI senkronu)
  const sendAudioState = useCallback((s: nativeAudio.AudioState) => {
    webviewRef.current?.injectJavaScript(`
      (function(){
        window.dispatchEvent(new MessageEvent('message', {
          data: JSON.stringify({ type: 'AUDIO_STATE', playing: ${s.playing ? 'true' : 'false'},
            id: ${s.id ? `'${String(s.id).replace(/[^a-z0-9_]/gi, '')}'` : 'null'},
            reason: '${s.reason || 'user'}' })
        }));
        true;
      })();
    `);
  }, []);

  // Android geri tuşu — WebView geçmişinde geri git
  useEffect(() => {
    const onBack = () => {
      if (status === 'error') {
        // Hata ekranındayken geri tuşu = yeniden dene
        doRetry();
        return true;
      }
      if (webviewRef.current) {
        webviewRef.current.goBack();
        return true; // event tüketildi
      }
      return false;
    };
    const sub = BackHandler.addEventListener('hardwareBackPress', onBack);
    return () => sub.remove();
  }, [status]);

  // Yükleme başladığında watchdog kur — sonsuz spinner'ı engelle
  const armWatchdog = useCallback(() => {
    if (watchdogTimer.current) clearTimeout(watchdogTimer.current);
    watchdogTimer.current = setTimeout(() => {
      setStatus((s) => (s === 'ready' ? s : 'error'));
    }, LOAD_TIMEOUT_MS);
  }, []);

  const onLoadStart = useCallback(() => {
    setStatus((s) => (s === 'ready' ? s : 'loading'));
    armWatchdog();
  }, [armWatchdog]);

  const getPlanFromCustomerInfo = (customerInfo: any): 'yearly' | 'monthly' => {
    try {
      const ent = customerInfo?.entitlements?.active?.[PRO_ENTITLEMENT_ID] || customerInfo?.entitlements?.active?.['mışıl_baby_pro'];
      const prodId = ent?.productIdentifier || (Array.isArray(customerInfo?.activeSubscriptions) && customerInfo.activeSubscriptions[0]) || '';
      const lower = String(prodId).toLowerCase();
      if (lower.includes('year') || lower.includes('annual')) return 'yearly';
      return 'monthly';
    } catch {
      return 'monthly';
    }
  };

  // ADIM 4 — Native tarafta CANLI lisans doğrulaması.
  // RevenueCat customerInfo'daki gerçek hak durumunu WebView localStorage'ına yazar.
  // Aktifse Pro açık; süresi dolmuş/iptal ise Pro kilitlenir. Bebek adı/verisine
  // (mishil_baby_name / mishil_baby_bdate) KESİNLİKLE dokunmaz.
  const syncEntitlementToWebView = useCallback(async () => {
    try {
      const ready = await initRevenueCat();
      if (!ready) return; // anahtarsız / mock mod — abonelik bayrağını değiştirme
      const Purchases = require('react-native-purchases').default;
      const customerInfo = await Purchases.getCustomerInfo();
      const active = hasActiveEntitlement(customerInfo);
      const detectedPlan = active ? getPlanFromCustomerInfo(customerInfo) : null;
      const planLine = detectedPlan
        ? `localStorage.setItem('mishil_subscription_plan', '${detectedPlan}');`
        : '';
      webviewRef.current?.injectJavaScript(`
        (function() {
          try {
            localStorage.setItem('mishil_subscription_active', '${active ? 'true' : 'false'}');
            ${planLine}
            if (typeof updateSubscriptionStatusUI === 'function') updateSubscriptionStatusUI();
            ${active ? '' : `
            // Hak yok → Pro özelliği kilitle: açık Mışıl Dadı sekmesinden çık.
            if (typeof switchTab === 'function') {
              var coach = document.getElementById('view-coach');
              if (coach && coach.classList.contains('active')) switchTab('home');
            }`}
          } catch (e) {}
          true;
        })();
      `);
    } catch (e) {
      // Ağ / SDK hatası abonelik durumunu değiştirmemeli — sessiz geç.
    }
  }, []);

  // ADIM 4 — uygulama ön plana geldiğinde canlı lisans doğrulamasını tekrarla
  // (abonelik başka cihazda iptal/yenilenmiş olabilir).
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'active') void syncEntitlementToWebView();
    });
    return () => sub.remove();
  }, [syncEntitlementToWebView]);

  // Yalnızca BAŞARILI yükleme — hata sonrası tetiklenmez (onLoadEnd aksine)
  const onLoad = useCallback(() => {
    clearTimers();
    retryCountRef.current = 0;
    setStatus('ready');
    // Native olduğumuzu web tarafına bildir.
    // Abonelik durumu app.html içinde zaten localStorage'dan okunuyor; her açılışta
    // SUBSCRIPTION_RESULT event'i tetiklemek gereksiz toast'a yol açtığı için kaldırıldı.
    webviewRef.current?.injectJavaScript(`
      (function() {
        if (window.MishilNative) {
          window.MishilNative.isNative = true;
          // Ses çalma native tarafa taşındı (arka plan / kilitli ekran).
          // Sorun çıkarsa bu bayrağı false yapmak app.html'i HTMLAudio'ya döndürür.
          window.MishilNative.audioBridge = true;
        }
        true;
      })();
    `);
    // ADIM 4 — her başarılı yüklemede canlı lisans doğrulaması yap.
    void syncEntitlementToWebView();

    // Canlı mağaza fiyatlarını (RevenueCat Offerings) web tarafına dinamik aktar
    (async () => {
      try {
        const offerings = await getOfferings();
        const m = offerings.find(o => o.packageType === 'MONTHLY');
        const a = offerings.find(o => o.packageType === 'ANNUAL');
        const pricePayload = {
          monthly: m?.priceString || '₺149,99/ay',
          yearly: a?.priceString || '₺599,99/yıl',
        };
        webviewRef.current?.injectJavaScript(`
          (function() {
            window.__MISHIL_STORE_PRICES__ = ${JSON.stringify(pricePayload)};
            if (typeof window.applyStorePrices === 'function') {
              window.applyStorePrices(window.__MISHIL_STORE_PRICES__);
            }
            true;
          })();
        `);
      } catch (e) {}
    })();
  }, [syncEntitlementToWebView]);

  // Ana çerçeve hatası (TLS, DNS, 5xx, timeout) → cold-start için sessiz retry,
  // denemeler tükenince gömülü çevrimdışı sürüme düş (boş ekran yerine)
  const handleLoadFailure = useCallback(() => {
    clearTimers();
    if (useOffline) return; // zaten çevrimdışı sürümdeyiz
    if (retryCountRef.current < MAX_AUTO_RETRY) {
      setStatus('error');
      retryCountRef.current += 1;
      const delay = 2500 * retryCountRef.current; // 2.5s, 5s, 7.5s — Railway uyanana kadar
      autoRetryTimer.current = setTimeout(() => {
        setStatus('loading');
        armWatchdog();
        webviewRef.current?.reload();
      }, delay);
      return;
    }
    // Otomatik denemeler bitti
    if (HAS_OFFLINE_HTML) {
      setUseOffline(true);
      setStatus('ready');
      startReconnectProbe();
    } else {
      setStatus('error'); // gömülü sürüm yoksa "Tekrar Dene" ekranında kal
    }
  }, [armWatchdog, useOffline, startReconnectProbe]);

  const onError = useCallback((e: any) => {
    // Alt kaynak (font/ses) hatalarını yok say; sadece ana doküman hatası önemli
    const ne = e?.nativeEvent;
    if (ne && ne.url && !String(ne.url).startsWith('https://mishil-production.up.railway.app')) return;
    handleLoadFailure();
  }, [handleLoadFailure]);

  const onHttpError = useCallback((e: any) => {
    const ne = e?.nativeEvent;
    // Yalnızca ana sayfa isteği 5xx/404 dönerse hata say
    if (ne && ne.url && ne.url !== MISHIL_WEB_URL) return;
    if (ne && ne.statusCode && ne.statusCode < 500 && ne.statusCode !== 404) return;
    handleLoadFailure();
  }, [handleLoadFailure]);

  // Android: WebView render süreci öldürüldü (düşük RAM'li cihazlarda OOM)
  // Bu yakalanmazsa uygulama komple çöker ("uygulama açılmıyor / kapanıyor")
  const onRenderProcessGone = useCallback((e: any) => {
    e?.preventDefault?.();
    setStatus('loading');
    armWatchdog();
    // ref üzerinden yeniden yükle; render süreci gittiği için reload() güvenli
    setTimeout(() => webviewRef.current?.reload(), 300);
    return true;
  }, [armWatchdog]);

  // iOS eşdeğeri
  const onContentProcessDidTerminate = useCallback(() => {
    setStatus('loading');
    armWatchdog();
    setTimeout(() => webviewRef.current?.reload(), 300);
  }, [armWatchdog]);

  const doRetry = useCallback(() => {
    clearTimers();
    stopReconnectProbe();
    retryCountRef.current = 0;
    setStatus('loading');
    armWatchdog();
    if (useOffline) {
      setUseOffline(false); // source {uri}'ye döner, kendisi yeniden yükler
    } else {
      webviewRef.current?.reload();
    }
  }, [armWatchdog, useOffline]);

  // Haptik yardımcı
  const triggerHaptic = async (level: string) => {
    try {
      if (level === 'heavy') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
      else if (level === 'medium') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      else await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch {}
  };

  // Web tarafına güvenli toast gönder
  const webToast = useCallback((text: string) => {
    const safe = String(text).replace(/[`\\$]/g, '');
    webviewRef.current?.injectJavaScript(
      `(function(){ typeof showToast === 'function' && showToast('${safe}'); true; })();`
    );
  }, []);

  // Pro'yu YALNIZCA doğrulanmış satın alma/geri yükleme sonrası aç
  const grantProInWebView = useCallback((plan: string | null, text: string) => {
    const safe = String(text).replace(/[`\\$]/g, '');
    const planLine = plan
      ? `localStorage.setItem('mishil_subscription_plan', '${String(plan).replace(/[^a-z]/gi, '')}');`
      : '';
    webviewRef.current?.injectJavaScript(`
      (function() {
        try {
          localStorage.setItem('mishil_onboarding_completed', 'true');
          localStorage.setItem('mishil_subscription_active', 'true');
          ${planLine}
          var screen = document.getElementById('screen-onboarding');
          if (screen) screen.classList.remove('active');
          var renewalModal = document.getElementById('vip-renewal-modal');
          if (renewalModal) renewalModal.classList.remove('active');
          if (typeof updateSubscriptionStatusUI === 'function') updateSubscriptionStatusUI();
          if (typeof renderAllViews === 'function') renderAllViews();
          typeof showToast === 'function' && showToast('${safe}');
        } catch (e) {}
        true;
      })();
    `);
  }, []);

  // JS Bridge mesaj handler
  const onMessage = useCallback(async (event: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);

      switch (msg.type) {
        case 'HAPTIC':
          await triggerHaptic(msg.level || 'light');
          break;

        case 'AUDIO_PLAY':
          // { id, url } — url app.html tarafında mutlak hâle getirilir
          if (msg.id && msg.url) {
            await nativeAudio.playSound(String(msg.id), String(msg.url), sendAudioState);
          }
          break;

        case 'AUDIO_STOP':
          await nativeAudio.stopSound(sendAudioState, 'user');
          break;

        case 'AUDIO_TIMER':
          nativeAudio.startTimer(Number(msg.minutes) || 0, sendAudioState);
          break;

        case 'AUDIO_VOLUME':
          await nativeAudio.setVolume(Number(msg.value));
          break;

        case 'PURCHASE_PACKAGE': {
          // Google Play / App Store IAP başlat
          const plan = msg.plan || 'monthly';
          const offerings = await getOfferings();
          const pkg = offerings.find(o =>
            plan === 'yearly' ? o.packageType === 'ANNUAL' : o.packageType === 'MONTHLY'
          );

          const result = await purchasePackage(pkg?.identifier || plan, pkg?.rawPackage);

          if (result.success && result.isActive) {
            // Yalnızca GERÇEKTEN aktif hak varsa VIP'yi aç
            grantProInWebView(plan, '🎉 Mışıl VIP aktif edildi!');
          } else if (result.cancelled) {
            // Kullanıcı iptal etti — sessiz geç
          } else {
            const isIOS = Platform.OS === 'ios';
            const storeName = isIOS ? 'App Store' : 'Google Play';
            const accountRef = isIOS ? 'Apple Kimliğinizi veya internet bağlantınızı' : 'Google Play test hesabınızı veya internet bağlantınızı';
            const errDetail = result.error ? ` (${result.error})` : '';
            webToast(
              result.error === 'no_package'
                ? `⚠️ Abonelik paketleri ${storeName}'dan yüklenemedi. Lütfen ${accountRef} kontrol edin.`
                : `⚠️ Satın alma tamamlanamadı${errDetail}. Bir ücret alınmadıysa tekrar deneyebilirsiniz.`
            );
          }
          break;
        }

        case 'RESTORE_PURCHASES': {
          const result = await restorePurchases();
          if (result.success && result.isActive) {
            let detectedPlan: 'yearly' | 'monthly' = 'monthly';
            try {
              const Purchases = require('react-native-purchases').default;
              const customerInfo = await Purchases.getCustomerInfo();
              detectedPlan = getPlanFromCustomerInfo(customerInfo);
            } catch {}
            grantProInWebView(detectedPlan, '✅ Satın alımlar geri yüklendi (Mışıl Baby Pro Aktif)');
          } else {
            webToast('ℹ️ Bu hesapta geri yüklenecek aktif bir abonelik bulunamadı.');
          }
          break;
        }

        case 'MANAGE_SUBSCRIPTIONS': {
          const url = Platform.OS === 'ios'
            ? 'https://apps.apple.com/account/subscriptions'
            : 'https://play.google.com/store/account/subscriptions';
          await Linking.openURL(url).catch(err => console.warn('Abonelik yönetimi açılamadı:', err));
          break;
        }

        case 'OPEN_URL': {
          if (msg.url) {
            await Linking.openURL(String(msg.url)).catch(err => console.warn('Bağlantı açılamadı:', err));
          }
          break;
        }

        default:
          break;
      }
    } catch (e) {
      // Sessizce geç
    }
  }, [webToast, grantProInWebView, sendAudioState]);

  const autoRetrying = status === 'error' && retryCountRef.current > 0 && retryCountRef.current <= MAX_AUTO_RETRY;

  // Hata durumunda gösterilecek ekran — GERÇEK yeniden deneme butonu ile
  const renderError = () => (
    <View style={styles.errorContainer}>
      <Text style={styles.errorIcon}>🌙</Text>
      <Text style={styles.errorTitle}>Bağlantı Kurulamadı</Text>
      <Text style={styles.errorSub}>
        İnternet bağlantınızı kontrol edin.{'\n'}
        {autoRetrying
          ? 'Sunucuya yeniden bağlanılıyor...'
          : 'Aşağıdaki butonla tekrar deneyebilirsiniz.'}
      </Text>
      {autoRetrying ? (
        <ActivityIndicator size="small" color="#E8A855" style={{ marginTop: 20 }} />
      ) : (
        <Pressable style={styles.retryBtn} onPress={doRetry} accessibilityRole="button">
          <Text style={styles.retryBtnText}>Tekrar Dene</Text>
        </Pressable>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0B0E17" />

      <WebView
        ref={webviewRef}
        source={
          useOffline
            ? { html: OFFLINE_HTML, baseUrl: MISHIL_WEB_ORIGIN }
            : { uri: MISHIL_WEB_URL }
        }
        style={styles.webview}
        injectedJavaScriptBeforeContentLoaded={INJECT_APP_META}
        onLoadStart={onLoadStart}
        onLoad={onLoad}
        onError={onError}
        onHttpError={onHttpError}
        onRenderProcessGone={onRenderProcessGone}
        onContentProcessDidTerminate={onContentProcessDidTerminate}
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
        mixedContentMode="never"

        // Harici pencere açan bağlantılar boş popup'ta takılmasın
        setSupportMultipleWindows={false}

        // Android render katmanı: donanım katmanı modern cihazlarda (özellikle Samsung)
        // çok daha akıcı. Yazılım katmanı yalnızca Android <9 (eski WebView boş ekran
        // bug'ı) için — 9+ donanım.
        androidLayerType={Number(Platform.Version) < 28 ? 'software' : 'hardware'}

        // URL değişikliklerinde izin ver
        onShouldStartLoadWithRequest={() => true}
      />

      {useOffline && (
        <Pressable style={styles.offlineBanner} onPress={doRetry} accessibilityRole="button">
          <Text style={styles.offlineBannerText}>
            📴 Çevrimdışı sürüm • yeniden bağlanılıyor — dokunup tekrar dene
          </Text>
        </Pressable>
      )}

      {status === 'error' && renderError()}
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
  offlineBanner: {
    position: 'absolute',
    top: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) : 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(232,168,85,0.95)',
    paddingVertical: 6,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  offlineBannerText: {
    color: '#0B0F19',
    fontSize: 12,
    fontWeight: '600',
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
  retryBtn: {
    marginTop: 24,
    paddingVertical: 14,
    paddingHorizontal: 36,
    borderRadius: 14,
    backgroundColor: '#E8A855',
  },
  retryBtnText: {
    color: '#0B0F19',
    fontSize: 15,
    fontWeight: '700',
  },
});
