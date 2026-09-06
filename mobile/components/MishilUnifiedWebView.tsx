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
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import * as Haptics from 'expo-haptics';
import { initRevenueCat, purchasePackage, restorePurchases, getOfferings } from '../features/subscription/revenuecat';
import * as nativeAudio from '../features/audio/nativeAudioPlayer';
import { OFFLINE_HTML } from '../features/webview/offlineHtml.generated';

// Railway canlı URL
const MISHIL_WEB_ORIGIN = 'https://mishil-production.up.railway.app';
const MISHIL_WEB_URL = `${MISHIL_WEB_ORIGIN}/app`;

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
  }, []);

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
        localStorage.setItem('misil_onboarding_completed', 'true');
        localStorage.setItem('mishil_subscription_active', 'true');
        ${planLine}
        var screen = document.getElementById('screen-onboarding');
        if (screen) screen.classList.remove('active');
        typeof showToast === 'function' && showToast('${safe}');
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
          // Google Play IAP başlat
          const plan = msg.plan || 'yearly';
          const offerings = await getOfferings();
          const pkg = offerings.find(o =>
            plan === 'yearly' ? o.packageType === 'ANNUAL'
            : plan === 'monthly' ? o.packageType === 'MONTHLY'
            : o.packageType === 'LIFETIME'
          );

          const result = await purchasePackage(pkg?.identifier || plan, pkg?.rawPackage);

          if (result.success && result.isActive) {
            // Yalnızca GERÇEKTEN aktif hak varsa Pro'yu aç
            grantProInWebView(plan, '🎉 Mışıl Baby Pro aktif edildi!');
          } else if (result.cancelled) {
            // Kullanıcı iptal etti — sessiz geç
          } else {
            webToast(
              result.error === 'no_package'
                ? '⚠️ Abonelik paketleri şu an yüklenemedi. Lütfen tekrar deneyin.'
                : '⚠️ Satın alma tamamlanamadı. Bir ücret alınmadıysa tekrar deneyebilirsiniz.'
            );
          }
          break;
        }

        case 'RESTORE_PURCHASES': {
          const result = await restorePurchases();
          if (result.success && result.isActive) {
            grantProInWebView(null, '✅ Satın alımlar geri yüklendi (Mışıl Baby Pro Aktif)');
          } else {
            webToast('ℹ️ Bu hesapta geri yüklenecek aktif bir abonelik bulunamadı.');
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

        // Android render katmanı: bazı GPU'larda "hardware" boş ekrana yol açtığından
        // yazılım katmanına alındı (animasyon perf. kaybı kabul edilebilir seviyede)
        androidLayerType="software"

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
