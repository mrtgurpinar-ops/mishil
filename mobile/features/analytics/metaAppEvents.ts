import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { IntroEligibilityState } from '../subscription/revenuecat';

export const META_APP_ID = '1093539003520092';
export const META_LOGGED_TX_STORAGE_KEY = '@mishil_meta_logged_tx_ids_v1';
const MAX_STORED_TX_IDS = 50;

export interface MetaPurchaseLogInput {
  plan: 'monthly' | 'yearly';
  price?: number;
  introPrice?: number;
  introEligibility?: IntroEligibilityState;
  periodType?: string;
  currencyCode?: string;
  isIntroOffer?: boolean;
  productId?: string;
  transactionId?: string;
  fallbackDedupKey?: string;
}

export interface MetaPurchaseLogResult {
  logged: boolean;
  reason?: string;
  amount?: number;
  currency?: string;
  transactionId?: string;
  isIntroOffer?: boolean;
}

let isMetaInitialized = false;
let cachedTrackingGranted = false;
let activeInitPromise: Promise<{ initialized: boolean; trackingGranted: boolean }> | null = null;
let lastActivateAppLoggedAt = 0;
const ACTIVATE_APP_MIN_INTERVAL_MS = 15_000;
const inMemoryLoggedTxIds = new Set<string>();
const inFlightTxIds = new Set<string>();

function getFbSdkModules(): { Settings: any; AppEventsLogger: any; AppLink?: any } | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fbsdk = require('react-native-fbsdk-next');
    if (!fbsdk || !fbsdk.Settings || !fbsdk.AppEventsLogger) {
      return null;
    }
    return {
      Settings: fbsdk.Settings,
      AppEventsLogger: fbsdk.AppEventsLogger,
      AppLink: fbsdk.AppLink,
    };
  } catch {
    return null;
  }
}

function getTrackingTransparencyModule(): {
  getTrackingPermissionsAsync?: () => Promise<{ status?: string; granted?: boolean }>;
  requestTrackingPermissionsAsync?: () => Promise<{ status?: string; granted?: boolean }>;
} | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require('expo-tracking-transparency');
  } catch {
    return null;
  }
}

async function hasTransactionBeenLoggedInStorage(txId: string): Promise<boolean> {
  if (!txId) return false;
  if (inMemoryLoggedTxIds.has(txId)) return true;
  try {
    const raw = await AsyncStorage.getItem(META_LOGGED_TX_STORAGE_KEY);
    if (!raw) return false;
    const list = JSON.parse(raw);
    if (Array.isArray(list) && list.includes(txId)) {
      inMemoryLoggedTxIds.add(txId);
      return true;
    }
  } catch {}
  return false;
}

async function persistLoggedTransaction(txId: string): Promise<void> {
  if (!txId) return;
  inMemoryLoggedTxIds.add(txId);
  try {
    const raw = await AsyncStorage.getItem(META_LOGGED_TX_STORAGE_KEY);
    const list: string[] = raw ? JSON.parse(raw) : [];
    const safeList = Array.isArray(list) ? list.filter((x) => typeof x === 'string') : [];
    if (!safeList.includes(txId)) {
      safeList.push(txId);
    }
    const trimmed = safeList.slice(-MAX_STORED_TX_IDS);
    await AsyncStorage.setItem(META_LOGGED_TX_STORAGE_KEY, JSON.stringify(trimmed));
  } catch {}
}

/**
 * Apple Guideline 5.1.2(i) uyumlu Meta SDK & SKAdNetwork başlatıcısı:
 * - Derleme zamanında `isAutoInitEnabled: false`, `autoLogAppEventsEnabled: false`, `advertiserIDCollectionEnabled: false`
 *   olduğu için ATT izni çözümlenmeden native SDK hiçbir ağ isteği başlatmaz.
 * - Eşzamanlı çağrılar aynı `activeInitPromise` sözünü paylaşır ve tamamlandığında `cachedTrackingGranted` döner.
 */
export async function initMetaSdkAndActivateApp(): Promise<{ initialized: boolean; trackingGranted: boolean }> {
  if (isMetaInitialized) {
    // SDK zaten başlatıldıysa (ör. Android RootLayout soğuk başlangıç veya arka plandan ön plana dönüş),
    // en az 15sn aralıkla fb_mobile_activate_app sinyalini tekrar gönder ve flush et.
    const now = Date.now();
    if (now - lastActivateAppLoggedAt >= ACTIVATE_APP_MIN_INTERVAL_MS) {
      try {
        const fb = getFbSdkModules();
        if (fb) {
          fb.AppEventsLogger.logEvent('fb_mobile_activate_app', {
            platform: Platform.OS,
          });
          if (typeof fb.AppEventsLogger.flush === 'function') {
            fb.AppEventsLogger.flush();
          }
          lastActivateAppLoggedAt = now;
        }
      } catch {}
    }
    return { initialized: true, trackingGranted: cachedTrackingGranted };
  }
  if (activeInitPromise) {
    return activeInitPromise;
  }

  activeInitPromise = (async () => {
    try {
      const fb = getFbSdkModules();
      if (!fb) {
        return { initialized: false, trackingGranted: false };
      }

      let trackingGranted = Platform.OS !== 'ios';

      if (Platform.OS === 'ios') {
        const att = getTrackingTransparencyModule();
        if (att && typeof att.requestTrackingPermissionsAsync === 'function') {
          try {
            const perm = await att.requestTrackingPermissionsAsync();
            trackingGranted = Boolean(perm?.granted || perm?.status === 'granted');
          } catch {
            trackingGranted = false;
          }
        } else {
          trackingGranted = false;
        }

        try {
          if (typeof fb.Settings.setAdvertiserTrackingEnabled === 'function') {
            await fb.Settings.setAdvertiserTrackingEnabled(trackingGranted);
          }
        } catch {}
      }

      try {
        if (typeof fb.Settings.setAdvertiserIDCollectionEnabled === 'function') {
          fb.Settings.setAdvertiserIDCollectionEnabled(trackingGranted);
        }
        if (typeof fb.Settings.setAutoLogAppEventsEnabled === 'function') {
          fb.Settings.setAutoLogAppEventsEnabled(true);
        }
        if (typeof fb.Settings.initializeSDK === 'function') {
          fb.Settings.initializeSDK();
        }
      } catch {}

      // YALNIZCA Android: Ertelenmiş derin bağlantı (Deferred App Link / Meta Ad Click) yakalayıcısı.
      // iOS'taki çalışan ve Apple tarafından onaylanmış ATT/SKAdNetwork akışına hiç dokunmamak ve
      // fb_mobile_activate_app olayını ağ çağrısıyla bekletmemek için fire-and-forget olarak yalnız Android'de tetiklenir.
      if (Platform.OS === 'android' && fb.AppLink && typeof fb.AppLink.fetchDeferredAppLink === 'function') {
        try {
          Promise.resolve(fb.AppLink.fetchDeferredAppLink()).catch(() => {});
        } catch {}
      }

      try {
        fb.AppEventsLogger.logEvent('fb_mobile_activate_app', {
          platform: Platform.OS,
        });
        if (typeof fb.AppEventsLogger.flush === 'function') {
          fb.AppEventsLogger.flush();
        }
        lastActivateAppLoggedAt = Date.now();
      } catch {}

      cachedTrackingGranted = trackingGranted;
      isMetaInitialized = true;
      return { initialized: true, trackingGranted };
    } catch {
      return { initialized: false, trackingGranted: false };
    } finally {
      activeInitPromise = null;
    }
  })();

  return activeInitPromise;
}

/**
 * Ebeveyn onboarding anketini tamamladığında Meta standart kayıt tamamlama olayını ateşler.
 */
export function logMetaOnboardingCompleted(): boolean {
  try {
    const fb = getFbSdkModules();
    if (!fb) return false;
    fb.AppEventsLogger.logEvent('fb_mobile_complete_registration', {
      fb_registration_method: 'onboarding_quiz',
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Kullanıcının ödediği gerçek abonelik tutarını (örn. İlk Ay 49.99 TRY, Standart Aylık 149.99 TRY, Yıllık 599.99 TRY)
 * çözer. iOS'ta yeni kullanıcılarda StoreKit `introEligibility === 'unknown'` döndüğünde ve `introPrice > 0`
 * tanımlı olduğunda (ve `periodType` açıkça `NORMAL` değilse veya `isIntroOffer` belirtilmişse) 49.99 indirimli fiyatı baz alır.
 */
export function resolveTransactedSubscriptionPrice(input: MetaPurchaseLogInput): {
  amount: number;
  isIntroOffer: boolean;
} {
  const plan = input.plan === 'yearly' ? 'yearly' : 'monthly';
  const periodUpper = String(input.periodType || '').trim().toUpperCase();
  const hasValidIntroPrice =
    typeof input.introPrice === 'number' && Number.isFinite(input.introPrice) && input.introPrice > 0;

  let isIntro = Boolean(input.isIntroOffer);
  if (!isIntro && plan === 'monthly') {
    if (periodUpper === 'INTRO' || periodUpper === 'INTRODUCTORY') {
      isIntro = true;
    } else if (
      hasValidIntroPrice &&
      input.introEligibility !== 'ineligible' &&
      (input.introEligibility === 'eligible' || (input.introEligibility === 'unknown' && periodUpper !== 'NORMAL'))
    ) {
      isIntro = true;
    }
  }

  let candidatePrice: number | undefined;
  if (isIntro && hasValidIntroPrice) {
    candidatePrice = input.introPrice;
  } else if (typeof input.price === 'number' && Number.isFinite(input.price) && input.price > 0) {
    candidatePrice = input.price;
  }

  const finalAmount =
    typeof candidatePrice === 'number' && candidatePrice > 0
      ? Number(candidatePrice.toFixed(2))
      : plan === 'yearly'
        ? 599.99
        : isIntro
          ? 49.99
          : 149.99;

  return {
    amount: finalAmount,
    isIntroOffer: isIntro,
  };
}

/**
 * Gerçek tahsil edilen abonelik tutarını ve işlem kimliğini (transactionId) senkron in-flight kilidi +
 * AsyncStorage kalıcılığıyla tekilleştirerek Meta'ya bildirir.
 * - ROAS çift sayımını (double-counting) önlemek için değer (`amount` + `currency`) yalnızca `logPurchase`
 *   üzerinden bildirilir; `Subscribe` olayı parasal `valueToSum` olmadan parametreleriyle gönderilir.
 * - NOT: `restorePurchases` akışında ASLA çağrılmamalıdır.
 */
export async function logMetaSubscriptionPurchase(
  input: MetaPurchaseLogInput
): Promise<MetaPurchaseLogResult> {
  const fb = getFbSdkModules();
  if (!fb) {
    return { logged: false, reason: 'sdk_unavailable' };
  }

  const plan = input.plan === 'yearly' ? 'yearly' : 'monthly';
  const productId = (input.productId || (plan === 'yearly' ? 'misil_annual' : 'misil_monthly')).trim();
  const rawTxId = typeof input.transactionId === 'string' ? input.transactionId.trim() : '';
  const fallbackKey = typeof input.fallbackDedupKey === 'string' ? input.fallbackDedupKey.trim() : '';
  const dedupKey = rawTxId || fallbackKey || `${productId}_${plan}_session_once`;

  // Senkron yarış kilidi: Eşzamanlı iki çağrı aynı dedupKey ile gelirse ikincisi await öncesinde anında elenir
  if (inMemoryLoggedTxIds.has(dedupKey) || inFlightTxIds.has(dedupKey)) {
    return { logged: false, reason: 'duplicate_transaction', transactionId: dedupKey };
  }
  inFlightTxIds.add(dedupKey);

  try {
    if (await hasTransactionBeenLoggedInStorage(dedupKey)) {
      return { logged: false, reason: 'duplicate_transaction', transactionId: dedupKey };
    }

    const { amount: rawPrice, isIntroOffer } = resolveTransactedSubscriptionPrice(input);
    const currency =
      typeof input.currencyCode === 'string' && input.currencyCode.trim().length === 3
        ? input.currencyCode.trim().toUpperCase()
        : 'TRY';

    const eventParams: Record<string, string | number> = {
      fb_currency: currency,
      fb_content_id: productId,
      fb_content_type: 'subscription',
      subscription_plan: plan,
      is_intro_offer: isIntroOffer ? 1 : 0,
      fb_order_id: dedupKey,
    };

    // Bellekte hemen işaretle, ardından yerel depoya yaz
    inMemoryLoggedTxIds.add(dedupKey);
    await persistLoggedTransaction(dedupKey);

    // 1. Standart Meta `Subscribe` olayı (parasız valueToSum olmadan, ROAS çift sayımını önler)
    fb.AppEventsLogger.logEvent('Subscribe', eventParams);

    // 2. Standart Meta `Purchase` olayı (tekil gelir / ROAS kaynağı ve otomatik iOS AEM köprüsü)
    fb.AppEventsLogger.logPurchase(rawPrice, currency, eventParams);

    if (typeof fb.AppEventsLogger.flush === 'function') {
      fb.AppEventsLogger.flush();
    }

    return {
      logged: true,
      amount: rawPrice,
      currency,
      transactionId: dedupKey,
      isIntroOffer,
    };
  } catch {
    inMemoryLoggedTxIds.delete(dedupKey);
    return { logged: false, reason: 'exception' };
  } finally {
    inFlightTxIds.delete(dedupKey);
  }
}

export function __resetMetaAppEventsForTests(): void {
  isMetaInitialized = false;
  cachedTrackingGranted = false;
  activeInitPromise = null;
  lastActivateAppLoggedAt = 0;
  inMemoryLoggedTxIds.clear();
  inFlightTxIds.clear();
}
