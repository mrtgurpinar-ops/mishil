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
import AsyncStorage from '@react-native-async-storage/async-storage';
import { initRevenueCat, purchasePackage, restorePurchases, getOfferings, hasActiveEntitlement, PRO_ENTITLEMENT_ID } from '../features/subscription/revenuecat';
import * as nativeAudio from '../features/audio/nativeAudioPlayer';
import { OFFLINE_HTML } from '../features/webview/offlineHtml.generated';
import {
  syncCareNotifications,
  getStoredNotificationSettings,
  saveStoredNotificationSettings,
  normalizeCareLang,
  CareLang,
} from '../features/notifications/careNotificationEngine';
import { storage, APP_LANG_KEY } from '../lib/storage';

function getSystemLocale(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().locale || 'tr-TR';
  } catch {
    return 'tr-TR';
  }
}

const DEVICE_LOCALE = getSystemLocale();
const DEVICE_LANG: CareLang = DEVICE_LOCALE.toLowerCase().startsWith('tr') ? 'tr' : 'en';

// Native sürüm bilgisini WebView'e sayfa yüklenmeden önce enjekte et (Settings sürüm rozeti + changelog dinamik)
const APP_VERSION = Constants.expoConfig?.version ?? '0.0.0';
const APP_BUILD =
  Platform.OS === 'ios'
    ? (Constants.expoConfig?.ios?.buildNumber ?? '0')
    : String(Constants.expoConfig?.android?.versionCode ?? '0');

// Railway canlı URL — Versiyon parametresi (?v=...) ile iOS WKWebView agresif önbelleği (cache) kırılır!
const MISHIL_WEB_ORIGIN = 'https://mishil-production.up.railway.app';
const MISHIL_WEB_URL = `${MISHIL_WEB_ORIGIN}/app?v=${APP_VERSION}_b${APP_BUILD}`;
const INJECT_APP_META = `
  window.__MISHIL_APP__ = {
    version: ${JSON.stringify(APP_VERSION)},
    build: ${JSON.stringify(APP_BUILD)},
    platform: ${JSON.stringify(Platform.OS)},
    deviceLocale: ${JSON.stringify(DEVICE_LOCALE)},
    deviceLang: ${JSON.stringify(DEVICE_LANG)},
    native: true
  };
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
  const [appLang, setAppLang] = useState<CareLang>(DEVICE_LANG);
  const appLangRef = useRef<CareLang>(DEVICE_LANG);
  const retryCountRef = useRef(0);
  const autoRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  // Satın alma akışı devam ederken arka plan kontrollerinin araya girip lisansı ezmesini önleyen işlem kilidi
  const isPurchaseInProgressRef = useRef(false);

  const updateNativeLang = useCallback((rawLang?: string | null) => {
    const norm = normalizeCareLang(rawLang || DEVICE_LANG);
    appLangRef.current = norm;
    setAppLang(norm);
    void storage.setAppLang(norm);
    return norm;
  }, []);

  useEffect(() => {
    storage.getAppLang().then((saved) => {
      if (saved) {
        appLangRef.current = saved;
        setAppLang(saved);
      }
    }).catch(() => {});
  }, []);

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
  // Satın alma sheet'i açıkken veya işlem devam ederken (isPurchaseInProgressRef) KESİNLİKLE çalışmaz!
  const syncEntitlementToWebView = useCallback(async () => {
    if (isPurchaseInProgressRef.current) return;
    try {
      const ready = await initRevenueCat();
      if (!ready) return; // anahtarsız / mock mod — abonelik bayrağını değiştirme
      const Purchases = require('react-native-purchases').default;
      const customerInfo = await Purchases.getCustomerInfo();
      const active = hasActiveEntitlement(customerInfo);
      const detectedPlan = active ? getPlanFromCustomerInfo(customerInfo) : null;
      const activeEnts = customerInfo?.entitlements?.active || {};
      const firstEntKey = Object.keys(activeEnts)[0];
      const firstEnt = firstEntKey ? activeEnts[firstEntKey] : null;
      const subMetaJson = active && firstEnt ? JSON.stringify({
        subscriberId: customerInfo?.originalAppUserId || undefined,
        productId: firstEnt?.productIdentifier || undefined,
        plan: detectedPlan || undefined,
        periodType: firstEnt?.periodType || 'TRIAL',
        store: firstEnt?.store || (Platform.OS === 'android' ? 'PLAY_STORE' : 'APP_STORE'),
        platform: Platform.OS === 'android' ? 'android' : 'ios',
        willRenew: firstEnt?.willRenew !== false,
        originalPurchaseDate: firstEnt?.originalPurchaseDate || undefined,
        expirationDate: firstEnt?.expirationDate || undefined,
      }) : 'null';
      const planLine = detectedPlan
        ? `localStorage.setItem('mishil_subscription_plan', '${detectedPlan}');`
        : '';
      webviewRef.current?.injectJavaScript(`
        (function() {
          try {
            if (${active ? 'true' : 'false'}) {
              localStorage.setItem('mishil_subscription_active', 'true');
              localStorage.setItem('mishil_rc_verified', 'true');
              localStorage.removeItem('mishil_limited_explore_mode');
              ${planLine}
              window.__MISHIL_SUB_META__ = ${subMetaJson};
              if (typeof window.syncSubscriberToAnalytics === 'function') {
                window.syncSubscriberToAnalytics(window.__MISHIL_SUB_META__);
              }
            } else {
              var isRev = localStorage.getItem('mishil_reviewer_bypass') === '1';
              var isFamVip = localStorage.getItem('mishil_subscription_plan') === 'family_vip';
              if (!isRev && !isFamVip) {
                localStorage.setItem('mishil_subscription_active', 'false');
                localStorage.removeItem('mishil_trial_start');
                localStorage.removeItem('mishil_rc_verified');
                localStorage.setItem('mishil_subscription_plan', 'free');
                window.__MISHIL_SUB_META__ = null;
                if (typeof switchTab === 'function') {
                  var coach = document.getElementById('view-coach');
                  var analyticsView = document.getElementById('view-analytics');
                  if ((coach && coach.classList.contains('active')) || (analyticsView && analyticsView.classList.contains('active'))) {
                    switchTab('home');
                  }
                }
              }
            }
            if (typeof loadBabyProfile === 'function') loadBabyProfile();
            if (typeof updateSubscriptionStatusUI === 'function') updateSubscriptionStatusUI();
            if (typeof renderAllViews === 'function') renderAllViews();
          } catch (e) {}
          true;
        })();
      `);
    } catch (e) {
      // Ağ / SDK hatası abonelik durumunu değiştirmemeli — sessiz geç.
    }
  }, []);

  // Uygulama ön plana geldiğinde canlı lisans doğrulaması (Satın alma sürerken ezmeyi engeller)
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'active' && !isPurchaseInProgressRef.current) {
        void syncEntitlementToWebView();
      }
    });
    return () => sub.remove();
  }, [syncEntitlementToWebView]);

  // RevenueCat resmi event dinleyicisi: Dekont veya abonelik değiştiğinde reaktif senkronizasyon
  useEffect(() => {
    let listener: ((info: any) => void) | null = null;
    let purchasesModule: any = null;

    (async () => {
      try {
        const ready = await initRevenueCat();
        if (!ready) return;
        purchasesModule = require('react-native-purchases').default;
        listener = (customerInfo: any) => {
          if (isPurchaseInProgressRef.current) return;
          const active = hasActiveEntitlement(customerInfo);
          const detectedPlan = active ? getPlanFromCustomerInfo(customerInfo) : null;
          const planLine = detectedPlan
            ? `localStorage.setItem('mishil_subscription_plan', '${detectedPlan}');`
            : '';
          webviewRef.current?.injectJavaScript(`
            (function() {
              try {
                if (${active ? 'true' : 'false'}) {
                  localStorage.setItem('mishil_subscription_active', 'true');
                  localStorage.setItem('mishil_rc_verified', 'true');
                  localStorage.removeItem('mishil_limited_explore_mode');
                  ${planLine}
                } else {
                  var isRev = localStorage.getItem('mishil_reviewer_bypass') === '1';
                  var isFamVip = localStorage.getItem('mishil_subscription_plan') === 'family_vip';
                  if (!isRev && !isFamVip) {
                    localStorage.setItem('mishil_subscription_active', 'false');
                    localStorage.removeItem('mishil_trial_start');
                    localStorage.removeItem('mishil_rc_verified');
                    localStorage.setItem('mishil_subscription_plan', 'free');
                  }
                }
                if (typeof loadBabyProfile === 'function') loadBabyProfile();
                if (typeof updateSubscriptionStatusUI === 'function') updateSubscriptionStatusUI();
                if (typeof renderAllViews === 'function') renderAllViews();
              } catch (e) {}
              true;
            })();
          `);
        };
        purchasesModule.addCustomerInfoUpdateListener(listener);
      } catch (e) {}
    })();

    return () => {
      if (listener && purchasesModule && typeof purchasesModule.removeCustomerInfoUpdateListener === 'function') {
        try {
          purchasesModule.removeCustomerInfoUpdateListener(listener);
        } catch (e) {}
      }
    };
  }, []);

  // AsyncStorage'dan profil ve onboarding durumunu WebView localStorage'ına hidrate et (Çift Katmanlı Koruma)
  const hydrateWebViewStorage = useCallback(async () => {
    try {
      const [[, rawProfile], [, rawOnboarding], [, rawPlan], [, rawSavedLang]] = await AsyncStorage.multiGet([
        '@mishil_baby_profile',
        '@mishil_onboarding_completed',
        '@mishil_subscription_plan',
        APP_LANG_KEY,
      ]);

      const resolvedSavedLang = rawSavedLang ? normalizeCareLang(rawSavedLang) : null;
      if (resolvedSavedLang) {
        appLangRef.current = resolvedSavedLang;
        setAppLang(resolvedSavedLang);
      }

      if (rawProfile || rawOnboarding === 'true' || resolvedSavedLang) {
        let pObj: any = null;
        try { pObj = rawProfile ? JSON.parse(rawProfile) : null; } catch {}
        const nameVal = pObj?.babyName ? String(pObj.babyName).replace(/[`\\$]/g, '') : '';
        const bdateVal = pObj?.babyBdate ? String(pObj.babyBdate).replace(/[`\\$]/g, '') : '';
        const roleVal = pObj?.userRole ? String(pObj.userRole).replace(/[`\\$]/g, '') : '';
        const uNameVal = pObj?.userName ? String(pObj.userName).replace(/[`\\$]/g, '') : '';
        const planVal = rawPlan ? String(rawPlan).replace(/[^a-z]/gi, '') : '';

        const script = `
          (function() {
            try {
              var modified = false;
              if (window.__MISHIL_APP__) {
                window.__MISHIL_APP__.savedLang = ${JSON.stringify(resolvedSavedLang)};
              }
              ${resolvedSavedLang ? `if (!localStorage.getItem('mishil_lang')) { localStorage.setItem('mishil_lang', '${resolvedSavedLang}'); modified = true; }` : ''}
              ${nameVal ? `if (!localStorage.getItem('mishil_baby_name')) { localStorage.setItem('mishil_baby_name', '${nameVal}'); modified = true; }` : ''}
              ${bdateVal ? `if (!localStorage.getItem('mishil_baby_bdate')) { localStorage.setItem('mishil_baby_bdate', '${bdateVal}'); modified = true; }` : ''}
              ${roleVal ? `if (!localStorage.getItem('mishil_user_role')) { localStorage.setItem('mishil_user_role', '${roleVal}'); modified = true; }` : ''}
              ${uNameVal ? `if (!localStorage.getItem('mishil_user_name')) { localStorage.setItem('mishil_user_name', '${uNameVal}'); modified = true; }` : ''}
              ${rawOnboarding === 'true' ? `if (!localStorage.getItem('mishil_onboarding_completed')) { localStorage.setItem('mishil_onboarding_completed', 'true'); modified = true; }` : ''}
              ${planVal ? `if (!localStorage.getItem('mishil_subscription_plan')) { localStorage.setItem('mishil_subscription_plan', '${planVal}'); modified = true; }` : ''}
              if (modified) {
                if (typeof window.applyLanguage === 'function') window.applyLanguage(localStorage.getItem('mishil_lang') || '${resolvedSavedLang || DEVICE_LANG}');
                if (typeof checkOnboardingState === 'function') checkOnboardingState();
                if (typeof loadBabyProfile === 'function') loadBabyProfile();
                if (typeof renderAllViews === 'function') renderAllViews();
              }
            } catch (e) {}
            true;
          })();
        `;
        webviewRef.current?.injectJavaScript(script);
      }
    } catch (e) {
      // Sessiz geç
    }
  }, []);

  // Yalnızca BAŞARILI yükleme — hata sonrası tetiklenmez (onLoadEnd aksine)
  const onLoad = useCallback(() => {
    clearTimers();
    retryCountRef.current = 0;
    setStatus('ready');
    // Native olduğumuzu web tarafına bildir ve yerel AsyncStorage'daki verileri hidrate et
    void hydrateWebViewStorage();
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
        const isEn = appLangRef.current === 'en';
        const pricePayload = {
          monthly: m?.priceString || (isEn ? '$4.99/mo' : '₺149,99/ay'),
          yearly: a?.priceString || (isEn ? '$29.99/yr' : '₺599,99/yıl'),
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

    // Bildirim ayarlarını ve 14 günlük bakım bildirimlerini OS kuyruğuna senkronize et
    (async () => {
      try {
        const rawProfile = await AsyncStorage.getItem('@mishil_baby_profile');
        let pObj: any = null;
        try { pObj = rawProfile ? JSON.parse(rawProfile) : null; } catch {}
        const notifSettings = await getStoredNotificationSettings();
        if (pObj?.babyName) {
          await syncCareNotifications(
            { babyName: pObj.babyName, babyBdate: pObj.babyBdate, lang: pObj.lang || appLangRef.current },
            notifSettings
          );
        }
        webviewRef.current?.injectJavaScript(`
          (function() {
            window.__MISHIL_NOTIFICATION_SETTINGS__ = ${JSON.stringify(notifSettings)};
            if (typeof window.applyNotificationSettings === 'function') {
              window.applyNotificationSettings(window.__MISHIL_NOTIFICATION_SETTINGS__);
            }
            true;
          })();
        `);
      } catch (e) {}
    })();
  }, [syncEntitlementToWebView, hydrateWebViewStorage]);

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

  // Haptik yardımcı (Haptics 2.0)
  const triggerHaptic = async (level: string) => {
    try {
      if (level === 'heavy') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
      else if (level === 'medium') await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      else if (level === 'success') await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      else if (level === 'selection') await Haptics.selectionAsync();
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
    // Native kalıcı depoya da yaz (Çift Katmanlı Koruma)
    void AsyncStorage.setItem('@mishil_onboarding_completed', 'true');
    void AsyncStorage.setItem('@mishil_subscription_active', 'true');
    void AsyncStorage.setItem('@mishil_trial_start', new Date().toISOString());
    if (plan) void AsyncStorage.setItem('@mishil_subscription_plan', String(plan));

    webviewRef.current?.injectJavaScript(`
      (function() {
        try {
          if (typeof window.clearStoreWatchdog === 'function') window.clearStoreWatchdog();
          else if (window.storeWatchdogTimer) { clearTimeout(window.storeWatchdogTimer); window.storeWatchdogTimer = null; }
          if (typeof resetPurchaseButtons === 'function') resetPurchaseButtons();
          if (typeof commitOnboardingProfile === 'function') commitOnboardingProfile();
          localStorage.setItem('mishil_onboarding_completed', 'true');
          localStorage.setItem('mishil_subscription_active', 'true');
          localStorage.setItem('mishil_trial_start', new Date().toISOString());
          ${planLine}
          var screen = document.getElementById('screen-onboarding');
          if (screen) screen.classList.remove('active');
          var renewalModal = document.getElementById('vip-renewal-modal');
          if (renewalModal) renewalModal.classList.remove('active');
          if (typeof loadBabyProfile === 'function') loadBabyProfile();
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
        case 'SET_LANGUAGE': {
          const nextLang = updateNativeLang(msg.lang || msg.payload?.lang);
          const rawProfile = await AsyncStorage.getItem('@mishil_baby_profile');
          let pObj: any = null;
          try { pObj = rawProfile ? JSON.parse(rawProfile) : null; } catch {}
          if (pObj) {
            pObj.lang = nextLang;
            void AsyncStorage.setItem('@mishil_baby_profile', JSON.stringify(pObj));
          }
          const notifSettings = await getStoredNotificationSettings();
          notifSettings.lang = nextLang;
          await saveStoredNotificationSettings({ lang: nextLang });
          await syncCareNotifications(
            { babyName: pObj?.babyName, babyBdate: pObj?.babyBdate, lang: nextLang },
            notifSettings
          );
          break;
        }

        case 'SYNC_CARE_NOTIFICATIONS':
        case 'SAVE_PROFILE':
          if (msg.payload) {
            const payloadLang = msg.payload.lang ? updateNativeLang(msg.payload.lang) : appLangRef.current;
            const profileToStore = { ...msg.payload, lang: payloadLang };
            void AsyncStorage.setItem('@mishil_baby_profile', JSON.stringify(profileToStore));
            void syncCareNotifications({
              babyName: msg.payload.babyName,
              babyBdate: msg.payload.babyBdate,
              lang: payloadLang,
            });
          }
          break;

        case 'UPDATE_NOTIFICATION_SETTINGS':
          if (msg.payload) {
            const nextLang = msg.payload.lang ? updateNativeLang(msg.payload.lang) : appLangRef.current;
            void saveStoredNotificationSettings({ ...msg.payload, lang: nextLang }).then(async (updatedSettings) => {
              const rawProfile = await AsyncStorage.getItem('@mishil_baby_profile');
              let pObj: any = null;
              try { pObj = rawProfile ? JSON.parse(rawProfile) : null; } catch {}
              await syncCareNotifications(
                { babyName: pObj?.babyName, babyBdate: pObj?.babyBdate, lang: nextLang },
                updatedSettings
              );
              webToast(nextLang === 'en' ? '✅ Notification preferences updated.' : '✅ Bildirim tercihleri güncellendi.');
            });
          }
          break;

        case 'ONBOARDING_COMPLETED':
          void AsyncStorage.setItem('@mishil_onboarding_completed', 'true');
          break;

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
          nativeAudio.startTimer(Number(msg.minutes) || 0, sendAudioState, msg.fadeOut !== false);
          break;

        case 'AUDIO_VOLUME':
          await nativeAudio.setVolume(Number(msg.value));
          break;

        case 'PURCHASE_PACKAGE': {
          isPurchaseInProgressRef.current = true;
          const isEn = appLangRef.current === 'en';
          // Web tarafına satın almanın native tarafta başladığını bildir
          webviewRef.current?.injectJavaScript(`
            (function() {
              if (window.MishilNative && typeof window.MishilNative.onPurchaseStarted === 'function') {
                window.MishilNative.onPurchaseStarted();
              }
              true;
            })();
          `);

          try {
            const plan = msg.plan || 'monthly';
            const offerings = await getOfferings();
            const pkg = offerings.find(o =>
              plan === 'yearly' ? o.packageType === 'ANNUAL' : o.packageType === 'MONTHLY'
            );

            let result = await purchasePackage(pkg?.identifier || plan, pkg?.rawPackage);

            // StoreKit Sandbox gecikmesi durumunda kısa bir retry sorgulaması (1.5 sn sonra)
            if (result.success && !result.isActive) {
              try {
                await new Promise(resolve => setTimeout(resolve, 1500));
                const Purchases = require('react-native-purchases').default;
                const info = await Purchases.getCustomerInfo();
                if (hasActiveEntitlement(info)) {
                  result = { success: true, isActive: true };
                }
              } catch (retryErr) {}
            }

            if (result.success && result.isActive) {
              // Yalnızca GERÇEKTEN aktif hak varsa VIP'yi aç
              grantProInWebView(plan, isEn ? '🎉 Mishil VIP activated!' : '🎉 Mışıl VIP aktif edildi!');
              const purchaseMeta = JSON.stringify({
                plan,
                productId: pkg?.identifier || (Platform.OS === 'android' ? (plan === 'yearly' ? 'misil' : 'misilaylik') : (plan === 'yearly' ? 'misil_annual' : 'misil_monthly')),
                platform: Platform.OS === 'android' ? 'android' : 'ios',
                store: Platform.OS === 'android' ? 'PLAY_STORE' : 'APP_STORE',
                periodType: 'TRIAL',
                isActive: true,
              });
              webviewRef.current?.injectJavaScript(`
                (function() {
                  window.__MISHIL_SUB_META__ = ${purchaseMeta};
                  if (window.MishilNative && typeof window.MishilNative.onPurchaseSuccess === 'function') {
                    window.MishilNative.onPurchaseSuccess(${purchaseMeta});
                  }
                  true;
                })();
              `);
              void syncEntitlementToWebView();
            } else if (result.cancelled) {
              // Kullanıcı ödeme penceresini kapattı veya vazgeçti — sıfır sahte hata, butonu sessizce normale döndür
              webviewRef.current?.injectJavaScript(`
                (function() {
                  if (window.MishilNative && typeof window.MishilNative.onPurchaseCancelled === 'function') {
                    window.MishilNative.onPurchaseCancelled();
                  } else if (typeof resetPurchaseButtons === 'function') {
                    resetPurchaseButtons();
                  }
                  true;
                })();
              `);
            } else {
              console.warn('[Purchase] Satın alma tamamlanamadı:', result.error);
              const isIOS = Platform.OS === 'ios';
              let errorMsg = isEn
                ? '⚠️ Purchase could not be completed. Please try again.'
                : '⚠️ Satın alma işlemi tamamlanamadı. Lütfen tekrar deneyiniz.';
              if (result.error === 'no_package') {
                errorMsg = isIOS
                  ? (isEn
                      ? '⚠️ Store package is preparing, please try again in a few seconds.'
                      : '⚠️ Mağaza paketi hazırlanıyor, lütfen birkaç saniye sonra tekrar deneyiniz.')
                  : (isEn
                      ? '⚠️ Could not connect to Google Play. Please verify your Google Play account and internet connection.'
                      : '⚠️ Google Play mağazasına bağlanılamadı. Lütfen cihazınızda Google Play hesabınızın açık olduğunu ve internet bağlantınızı kontrol ediniz.');
              } else if (isIOS) {
                errorMsg = isEn
                  ? '⚠️ Apple StoreKit transaction could not be completed. Please check your internet connection and Apple ID.'
                  : '⚠️ Apple StoreKit işlemi tamamlanamadı. Lütfen internet bağlantınızı ve Apple Kimliğinizi kontrol edip tekrar deneyiniz.';
              } else {
                errorMsg = isEn
                  ? '⚠️ Google Play billing could not be completed. Please check your Google Play Store account and try again.'
                  : '⚠️ Google Play ödeme işlemi tamamlanamadı. Lütfen Google Play Store uygulamasından hesabınızı kontrol edip tekrar deneyiniz.';
              }

              webviewRef.current?.injectJavaScript(`
                (function() {
                  if (window.MishilNative && typeof window.MishilNative.onPurchaseError === 'function') {
                    window.MishilNative.onPurchaseError('${errorMsg}');
                  } else {
                    if (typeof resetPurchaseButtons === 'function') resetPurchaseButtons();
                    if (typeof showToast === 'function') showToast('${errorMsg}');
                  }
                  true;
                })();
              `);
            }
          } finally {
            // İşlem bittiğinde kilidi kaldır, AppState artık güvenle çalışabilir
            isPurchaseInProgressRef.current = false;
          }
          break;
        }

        case 'RESTORE_PURCHASES': {
          const isEn = appLangRef.current === 'en';
          const result = await restorePurchases();
          if (result.success && result.isActive) {
            let detectedPlan: 'yearly' | 'monthly' = 'monthly';
            try {
              const Purchases = require('react-native-purchases').default;
              const customerInfo = await Purchases.getCustomerInfo();
              detectedPlan = getPlanFromCustomerInfo(customerInfo);
            } catch {}
            grantProInWebView(
              detectedPlan,
              isEn ? '✅ Purchases restored (Mishil Baby Pro Active)' : '✅ Satın alımlar geri yüklendi (Mışıl Baby Pro Aktif)'
            );
          } else {
            webToast(
              isEn ? 'ℹ️ No active subscription found on this account to restore.' : 'ℹ️ Bu hesapta geri yüklenecek aktif bir abonelik bulunamadı.'
            );
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
  }, [webToast, grantProInWebView, sendAudioState, updateNativeLang]);

  const autoRetrying = status === 'error' && retryCountRef.current > 0 && retryCountRef.current <= MAX_AUTO_RETRY;
  const isEnUI = appLang === 'en';

  // Hata durumunda gösterilecek ekran — GERÇEK yeniden deneme butonu ile
  const renderError = () => (
    <View style={styles.errorContainer}>
      <Text style={styles.errorIcon}>🌙</Text>
      <Text style={styles.errorTitle}>{isEnUI ? 'Connection Failed' : 'Bağlantı Kurulamadı'}</Text>
      <Text style={styles.errorSub}>
        {isEnUI ? 'Please check your internet connection.' : 'İnternet bağlantınızı kontrol edin.'}{'\n'}
        {autoRetrying
          ? (isEnUI ? 'Reconnecting to server...' : 'Sunucuya yeniden bağlanılıyor...')
          : (isEnUI ? 'You can try again using the button below.' : 'Aşağıdaki butonla tekrar deneyebilirsiniz.')}
      </Text>
      {autoRetrying ? (
        <ActivityIndicator size="small" color="#E8A855" style={{ marginTop: 20 }} />
      ) : (
        <Pressable style={styles.retryBtn} onPress={doRetry} accessibilityRole="button">
          <Text style={styles.retryBtnText}>{isEnUI ? 'Try Again' : 'Tekrar Dene'}</Text>
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
            <Text style={styles.loadingText}>
              {isEnUI ? 'Loading Mishil Baby...' : 'Mışıl Baby Yükleniyor...'}
            </Text>
          </View>
        )}
        startInLoadingState={true}
        javaScriptEnabled
        domStorageEnabled
        thirdPartyCookiesEnabled
        sharedCookiesEnabled
        cacheEnabled={true}
        cacheMode="LOAD_NO_CACHE"
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
            {isEnUI
              ? '📴 Offline mode • reconnecting — tap to retry'
              : '📴 Çevrimdışı sürüm • yeniden bağlanılıyor — dokunup tekrar dene'}
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
