import { Platform } from 'react-native';
import Constants from 'expo-constants';
import type {
  CustomerInfo,
  PurchasesPackage,
  PurchasesStoreTransaction,
} from 'react-native-purchases';

export type IntroEligibilityState = 'eligible' | 'ineligible' | 'unknown';

export interface PackageOffer {
  identifier: string;
  packageType: 'WEEKLY' | 'MONTHLY' | 'ANNUAL' | 'LIFETIME';
  priceString: string;
  price?: number;
  currencyCode?: string;
  introPriceString?: string;
  introPrice?: number;
  introEligibility?: IntroEligibilityState;
  title: string;
  description: string;
  rawPackage?: PurchasesPackage;
}

export interface PurchaseResult {
  success: boolean;      // akış hatasız tamamlandı mı
  isActive: boolean;     // kullanıcının GERÇEKTEN aktif bir hak sahibi olup olmadığı
  cancelled?: boolean;
  error?: string;
  customerInfo?: CustomerInfo;
  transaction?: PurchasesStoreTransaction;
}

// RevenueCat entitlement adı (panelde tanımlı). hasActiveEntitlement önce bunu arar.
export const PRO_ENTITLEMENT_ID = 'pro';

// Yalnızca GÖRÜNTÜLEME amaçlı yedek liste (offerings yüklenemezse).
// Gerçek ücretlendirme her zaman Google Play / App Store fiyatı üzerinden yapılır.
// identifier'lar RevenueCat default paket kimlikleriyle ($rc_*) hizalı.
// NOT: Bu stringler mağaza konsolundaki fiyatlarla senkron tutulmalıdır.
export const FALLBACK_OFFERINGS: PackageOffer[] = [
  {
    identifier: '$rc_monthly',
    packageType: 'MONTHLY',
    priceString: '₺149,99 / Ay',
    price: 149.99,
    currencyCode: 'TRY',
    introPriceString: '₺49,99',
    introPrice: 49.99,
    introEligibility: 'unknown',
    title: '🌙 Mışıl Baby Aylık VIP (Önerilen)',
    description: 'Yeni aboneler için ilk ay ₺49,99 • Sonrasında Aylık ₺149,99 • Otomatik yenilenir, mağazadan iptal.',
  },
  {
    identifier: '$rc_annual',
    packageType: 'ANNUAL',
    priceString: '₺599,99 / Yıl',
    price: 599.99,
    currencyCode: 'TRY',
    introEligibility: 'ineligible',
    title: '👑 Mışıl Baby Yıllık VIP (Tasarruflu)',
    description: 'Yıllık ₺599,99 • %67 Tasarruf (12 ay kesintisiz tam VIP) • Otomatik yenilenir.',
  },
];

let isConfigured = false;
let isRealKey = false;

const getApiKey = () => {
  if (Platform.OS === 'ios') {
    return process.env.EXPO_PUBLIC_REVENUECAT_IOS || Constants.expoConfig?.extra?.revenueCatApiKeyIos || 'appl_YErlYWqQcbRzipLuFKFliryZXAX';
  }
  return process.env.EXPO_PUBLIC_REVENUECAT_ANDROID || Constants.expoConfig?.extra?.revenueCatApiKeyAndroid || 'goog_LCNeMzKcaNSPdZModiKqmLtygYk';
};

export const initRevenueCat = async (userId?: string) => {
  if (isConfigured) return isRealKey;
  const apiKey = getApiKey();

  if (!apiKey || String(apiKey).includes('mock_key')) {
    console.warn('[RevenueCat] Geçerli public SDK anahtarı yok — satın alma devre dışı (mock mod).');
    isConfigured = true;
    isRealKey = false;
    return false;
  }

  try {
    const Purchases = require('react-native-purchases').default;
    const isIOS = Platform.OS === 'ios';
    await Purchases.configure({
      apiKey,
      appUserID: userId,
      ...(isIOS ? { usesStoreKit2IfAvailable: true } : {})
    });
    isConfigured = true;
    isRealKey = true;
    console.log(`[RevenueCat] ${isIOS ? 'App Store (StoreKit 2)' : 'Google Play Store'} ile yapılandırıldı.`);
    return true;
  } catch (e) {
    console.warn('[RevenueCat] Yapılandırma hatası:', e);
    isConfigured = true;
    isRealKey = false;
    return false;
  }
};

/** RevenueCat customerInfo üzerinden gerçekten aktif hak var mı? */
export const hasActiveEntitlement = (customerInfo: any): boolean => {
  if (!customerInfo) return false;
  // Öncelik: panelde tanımlı 'pro' veya 'mışıl_baby_pro' entitlement'ı aktif mi?
  if (customerInfo.entitlements?.active?.[PRO_ENTITLEMENT_ID] || customerInfo.entitlements?.active?.['mışıl_baby_pro']) {
    return true;
  }
  // Genel yedek (aktif abonelikler veya deneme periyodu)
  const activeEntitlements = customerInfo.entitlements?.active
    ? Object.keys(customerInfo.entitlements.active)
    : [];
  const activeSubs = Array.isArray(customerInfo.activeSubscriptions)
    ? customerInfo.activeSubscriptions
    : [];
  return activeEntitlements.length > 0 || activeSubs.length > 0;
};

function extractAndroidPaidIntroOption(product: any): {
  option: any | null;
  introPriceString?: string;
  introPrice?: number;
  eligibility: IntroEligibilityState;
} {
  try {
    const subsOpts: any[] = Array.isArray(product?.subscriptionOptions) ? product.subscriptionOptions : [];
    const basePrice = typeof product?.price === 'number' ? product.price : 0;
    let sawMissingRecurringPrice = false;
    for (const opt of subsOpts) {
      const phases: any[] = Array.isArray(opt?.pricingPhases) ? opt.pricingPhases : [];
      if (phases.length >= 2) {
        const p0 = phases[0]?.price;
        const pLast = phases[phases.length - 1]?.price;
        const micros0 = typeof p0?.amountMicros === 'number' ? p0.amountMicros : 0;
        const microsLast = typeof pLast?.amountMicros === 'number' && pLast.amountMicros > 0
          ? pLast.amountMicros
          : (basePrice > 0 ? Math.round(basePrice * 1_000_000) : 0);
        if (microsLast <= 0) {
          sawMissingRecurringPrice = true;
          continue;
        }
        // Yalnızca ÜCRETLİ indirimli ilk dönem teklifini (0 TL olmayan ve doğrulanmış normal fiyattan düşük) kabul et
        if (micros0 > 0 && micros0 < microsLast) {
          return {
            option: opt,
            introPriceString: p0?.formatted || undefined,
            introPrice: Number((micros0 / 1_000_000).toFixed(2)),
            eligibility: 'eligible',
          };
        }
      }
    }
    if (sawMissingRecurringPrice) {
      return { option: null, eligibility: 'unknown' };
    }
    if (subsOpts.length > 0) {
      return { option: null, eligibility: 'ineligible' };
    }
  } catch {}
  return { option: null, eligibility: 'unknown' };
}

export const getOfferings = async (): Promise<PackageOffer[]> => {
  try {
    const ready = await initRevenueCat();
    if (!ready) return FALLBACK_OFFERINGS;
    const Purchases = require('react-native-purchases').default;
    const offerings = await Purchases.getOfferings();
    if (offerings.current && offerings.current.availablePackages.length > 0) {
      const pkgs: any[] = offerings.current.availablePackages;
      let iosEligMap: Record<string, any> = {};
      if (Platform.OS === 'ios' && typeof Purchases.checkTrialOrIntroductoryPriceEligibility === 'function') {
        try {
          const prodIds = pkgs
            .map((p: any) => p?.product?.identifier)
            .filter((id: any): id is string => typeof id === 'string' && id.length > 0);
          if (prodIds.length > 0) {
            iosEligMap = (await Purchases.checkTrialOrIntroductoryPriceEligibility(prodIds)) || {};
          }
        } catch {}
      }

      return pkgs.map((pkg: any) => {
        const prod = pkg?.product || {};
        let introPriceString: string | undefined;
        let introPrice: number | undefined;
        let introEligibility: IntroEligibilityState = 'unknown';

        if (Platform.OS === 'ios') {
          const ip = prod.introPrice;
          const ipVal = typeof ip?.price === 'number' ? ip.price : 0;
          const eligEntry = prod.identifier ? iosEligMap[prod.identifier] : undefined;
          const statusNum = typeof eligEntry?.status === 'number' ? eligEntry.status : undefined;
          // Yalnızca ücretli (>0) introductory offer varsa dikkate al (0 TL eski denemeyi asla indirimli ilk ay sanma)
          if (ip && ipVal > 0) {
            introPriceString = ip.priceString || undefined;
            introPrice = ipVal;
            if (statusNum === 2) introEligibility = 'eligible';
            else if (statusNum === 1 || statusNum === 3) introEligibility = 'ineligible';
            else introEligibility = 'unknown';
          } else {
            introEligibility = 'ineligible';
          }
        } else {
          const gpIntro = extractAndroidPaidIntroOption(prod);
          introPriceString = gpIntro.introPriceString;
          introPrice = gpIntro.introPrice;
          introEligibility = gpIntro.eligibility;
        }

        return {
          identifier: pkg.identifier,
          packageType: pkg.packageType,
          priceString: prod.priceString || `${prod.currencyCode} ${prod.price}`,
          price: typeof prod.price === 'number' ? prod.price : undefined,
          currencyCode: prod.currencyCode || undefined,
          introPriceString,
          introPrice,
          introEligibility,
          title: prod.title,
          description: prod.description,
          rawPackage: pkg,
        };
      });
    }
  } catch (err) {
    console.log('[RevenueCat] Offerings alınamadı, yedek görüntüleme listesi:', err);
  }
  return FALLBACK_OFFERINGS;
};

export const purchasePackage = async (packageId: string, rawPackage?: any): Promise<PurchaseResult> => {
  try {
    const ready = await initRevenueCat();
    const Purchases = require('react-native-purchases').default;

    // 1. Yol: RevenueCat rawPackage varsa (Android'de uygun ücretli intro option varsa onu seçerek) çağır
    if (rawPackage) {
      if (Platform.OS === 'android' && Purchases.purchaseSubscriptionOption && rawPackage?.product) {
        const gpIntro = extractAndroidPaidIntroOption(rawPackage.product);
        if (gpIntro.option) {
          const optRes = await Purchases.purchaseSubscriptionOption(gpIntro.option);
          const optInfo = optRes?.customerInfo;
          return {
            success: true,
            isActive: hasActiveEntitlement(optInfo),
            customerInfo: optInfo,
            transaction: optRes?.transaction || optRes?.storeTransaction,
          };
        }
      }
      const purchaseRes = await Purchases.purchasePackage(rawPackage);
      const customerInfo = purchaseRes?.customerInfo;
      return {
        success: true,
        isActive: hasActiveEntitlement(customerInfo),
        customerInfo,
        transaction: purchaseRes?.transaction || purchaseRes?.storeTransaction,
      };
    }

    // 2. Yol: rawPackage yoksa (StoreKit / Google Play doğrudan çoklu ürün fallback'i)
    const isIOS = Platform.OS === 'ios';
    const isYearly = packageId.toLowerCase().includes('year') || packageId.toLowerCase().includes('annual') || packageId.toLowerCase() === 'misil';
    const candidateProductIds = Array.from(new Set([
      ...(isIOS
        ? (isYearly
            ? ['misil_annual', '$rc_annual', 'com.levitas.misilbaby.annual']
            : ['misil_monthly', '$rc_monthly', 'com.levitas.misilbaby.monthly'])
        : (isYearly
            ? ['misil', 'misil:misil', 'misil_annual', '$rc_annual', 'com.levitas.misilbaby.annual']
            : ['misilaylik', 'misilaylik:misilaylik', 'misil_monthly', '$rc_monthly', 'com.levitas.misilbaby.monthly'])
      ),
      packageId
    ]));

    if (ready && Purchases.getProducts) {
      try {
        console.log('[RevenueCat] Mağazada aranacak aday ürün ID\'leri:', candidateProductIds);
        const subCategory = Purchases.PRODUCT_CATEGORY?.SUBSCRIPTION || 'SUBSCRIPTION';
        const products = await Purchases.getProducts(candidateProductIds, subCategory);
        if (products && products.length > 0) {
          console.log('[RevenueCat] Eşleşen mağaza ürünü bulundu:', products[0].identifier);
          // Android Google Play Billing subscription option desteği
          let purchasePromise;
          if (Purchases.purchaseSubscriptionOption && products[0].defaultOption) {
            purchasePromise = Purchases.purchaseSubscriptionOption(products[0].defaultOption);
          } else {
            purchasePromise = Purchases.purchaseStoreProduct(products[0]);
          }
          const purchaseRes = await purchasePromise;
          const customerInfo = purchaseRes?.customerInfo;
          return {
            success: true,
            isActive: hasActiveEntitlement(customerInfo),
            customerInfo,
            transaction: purchaseRes?.transaction || purchaseRes?.storeTransaction,
          };
        } else {
          console.warn('[RevenueCat] Aday ID\'lerin hiçbiri mağazada bulunamadı:', candidateProductIds);
        }
      } catch (storeErr: any) {
        if (storeErr?.userCancelled) return { success: false, isActive: false, cancelled: true };
        console.warn('[RevenueCat] purchaseStoreProduct hatası:', storeErr);
        return { success: false, isActive: false, error: storeErr?.code ? String(storeErr.code) : 'store_error' };
      }
    }

    // Sadece geliştirme derlemesinde (Expo __DEV__) test kolaylığı için geç
    if (typeof __DEV__ !== 'undefined' && __DEV__) {
      console.warn('[RevenueCat] __DEV__ modu: test amaçlı başarı taklit ediliyor.');
      return { success: true, isActive: true };
    }

    return { success: false, isActive: false, error: 'no_package' };
  } catch (err: any) {
    if (err?.userCancelled) {
      return { success: false, isActive: false, cancelled: true };
    }
    console.warn('[RevenueCat] Satın alma hatası:', err);
    return { success: false, isActive: false, error: err?.code ? String(err.code) : 'purchase_failed' };
  }
};

export const restorePurchases = async (): Promise<PurchaseResult> => {
  try {
    const ready = await initRevenueCat();
    if (!ready) return { success: false, isActive: false, error: 'not_configured' };
    const Purchases = require('react-native-purchases').default;
    const customerInfo = await Purchases.restorePurchases();
    // restore "başarılı" olsa bile hak yoksa Pro AÇILMAMALI
    return { success: true, isActive: hasActiveEntitlement(customerInfo), customerInfo };
  } catch (err) {
    console.log('[RevenueCat] Geri yükleme hatası:', err);
    return { success: false, isActive: false, error: String(err) };
  }
};
