import { Platform } from 'react-native';
import Constants from 'expo-constants';
import type {
  CustomerInfo,
  PurchasesPackage,
  PurchasesStoreTransaction,
} from 'react-native-purchases';

export type IntroEligibilityState = 'eligible' | 'ineligible' | 'unknown';
export type IntroOfferType = 'free_trial' | 'paid_intro' | 'none';

export interface PackageOffer {
  identifier: string;
  offeringIdentifier?: string;
  productId?: string;
  packageType: 'WEEKLY' | 'MONTHLY' | 'ANNUAL' | 'LIFETIME';
  priceString: string;
  price?: number;
  currencyCode?: string;
  introPriceString?: string;
  introPrice?: number;
  introEligibility?: IntroEligibilityState;
  introOfferType?: IntroOfferType;
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
    introOfferType: 'paid_intro',
    title: '🌙 Mışıl Baby Aylık VIP (Önerilen)',
    description: 'Yeni aboneler için ilk ay ₺49,99 • Memnun kalırsanız Aylık ₺149,99 • Otomatik yenilenir, mağazadan iptal.',
  },
  {
    identifier: '$rc_annual',
    packageType: 'ANNUAL',
    priceString: '₺599,99 / Yıl',
    price: 599.99,
    currencyCode: 'TRY',
    introEligibility: 'ineligible',
    introOfferType: 'none',
    title: '👑 Mışıl Baby Yıllık VIP (Tasarruflu)',
    description: 'Yıllık ₺599,99 • Tüm yıl %67 indirim avantajı • Otomatik yenilenir.',
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
    // react-native-purchases v9+ iOS'ta varsayılan olarak StoreKit 2 kullanır
    await Purchases.configure({
      apiKey,
      appUserID: userId,
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

function extractAndroidIntroOption(product: any, packageIdentifier?: string, offeringIdentifier?: string): {
  option: any | null;
  introPriceString?: string;
  introPrice?: number;
  recurringPriceString?: string;
  recurringPrice?: number;
  eligibility: IntroEligibilityState;
  introOfferType: IntroOfferType;
} {
  try {
    const subsOpts: any[] = Array.isArray(product?.subscriptionOptions) ? product.subscriptionOptions : [];
    const basePrice = typeof product?.price === 'number' ? product.price : 0;
    let basePlanMicros = 0;
    let basePlanFormatted: string | undefined;
    for (const opt of subsOpts) {
      const phases: any[] = Array.isArray(opt?.pricingPhases) ? opt.pricingPhases : [];
      if (opt?.isBasePlan && phases.length === 1 && typeof phases[0]?.price?.amountMicros === 'number' && phases[0].price.amountMicros > 0) {
        basePlanMicros = phases[0].price.amountMicros;
        basePlanFormatted = phases[0].price.formatted || undefined;
        break;
      }
    }

    const combinedHints = `${String(packageIdentifier || '')} ${String(offeringIdentifier || '')} ${String(product?.identifier || '')}`.toLowerCase();
    const prefersFreeTrial = combinedHints.includes('free') || combinedHints.includes('trial') || combinedHints.includes('group_b') || combinedHints.includes('variant_b');
    const prefersPaidIntro = combinedHints.includes('intro') || combinedHints.includes('49') || combinedHints.includes('group_a') || combinedHints.includes('variant_a');

    type CandidateMatch = {
      option: any;
      introPriceString?: string;
      introPrice: number;
      recurringPriceString?: string;
      recurringPrice: number;
      eligibility: IntroEligibilityState;
      introOfferType: IntroOfferType;
      isDefaultOption: boolean;
    };

    const candidates: CandidateMatch[] = [];
    let sawMissingRecurringPrice = false;
    const defaultOptId = product?.defaultOption?.id;

    for (const opt of subsOpts) {
      const phases: any[] = Array.isArray(opt?.pricingPhases) ? opt.pricingPhases : [];
      if (phases.length >= 2) {
        const p0 = phases[0]?.price;
        const pLast = opt?.fullPricePhase?.price || phases[phases.length - 1]?.price;
        const micros0 = typeof p0?.amountMicros === 'number' ? p0.amountMicros : -1;
        const microsLast = typeof pLast?.amountMicros === 'number' && pLast.amountMicros > 0
          ? pLast.amountMicros
          : (basePlanMicros > 0 ? basePlanMicros : (basePrice > 0 ? Math.round(basePrice * 1_000_000) : 0));
        if (microsLast <= 0) {
          sawMissingRecurringPrice = true;
          continue;
        }
        // Evrensel A/B Teklif Motoru (Build 75):
        // 1) Grup B: micros0 === 0 -> İlk Ay Ücretsiz (free_trial)
        // 2) Grup A: micros0 > 0 && micros0 < microsLast -> İlk Ay İndirimli (paid_intro)
        if (micros0 === 0) {
          const currSym = (pLast?.formatted || basePlanFormatted || '').replace(/[0-9.,\s]+/g, '') || '₺';
          const zeroFormatted = (p0?.formatted && /\d/.test(String(p0.formatted))) ? p0.formatted : `${currSym}0`;
          candidates.push({
            option: opt,
            introPriceString: zeroFormatted,
            introPrice: 0,
            recurringPriceString: pLast?.formatted || basePlanFormatted || undefined,
            recurringPrice: Number((microsLast / 1_000_000).toFixed(2)),
            eligibility: 'eligible',
            introOfferType: 'free_trial',
            isDefaultOption: Boolean(defaultOptId && opt?.id === defaultOptId),
          });
        } else if (micros0 > 0 && micros0 < microsLast) {
          candidates.push({
            option: opt,
            introPriceString: p0?.formatted || undefined,
            introPrice: Number((micros0 / 1_000_000).toFixed(2)),
            recurringPriceString: pLast?.formatted || basePlanFormatted || undefined,
            recurringPrice: Number((microsLast / 1_000_000).toFixed(2)),
            eligibility: 'eligible',
            introOfferType: 'paid_intro',
            isDefaultOption: Boolean(defaultOptId && opt?.id === defaultOptId),
          });
        }
      }
    }

    if (candidates.length > 0) {
      let chosen = candidates[0];
      if (prefersFreeTrial) {
        chosen = candidates.find(c => c.introOfferType === 'free_trial') || chosen;
      } else if (prefersPaidIntro) {
        chosen = candidates.find(c => c.introOfferType === 'paid_intro') || chosen;
      } else {
        chosen = candidates.find(c => c.isDefaultOption) || candidates[0];
      }
      return {
        option: chosen.option,
        introPriceString: chosen.introPriceString,
        introPrice: chosen.introPrice,
        recurringPriceString: chosen.recurringPriceString,
        recurringPrice: chosen.recurringPrice,
        eligibility: chosen.eligibility,
        introOfferType: chosen.introOfferType,
      };
    }

    if (sawMissingRecurringPrice) {
      return { option: null, eligibility: 'unknown', introOfferType: 'none' };
    }
    if (subsOpts.length > 0) {
      return {
        option: null,
        recurringPriceString: basePlanFormatted,
        recurringPrice: basePlanMicros > 0 ? Number((basePlanMicros / 1_000_000).toFixed(2)) : undefined,
        eligibility: 'ineligible',
        introOfferType: 'none',
      };
    }
  } catch {}
  return { option: null, eligibility: 'unknown', introOfferType: 'none' };
}

const OFFERINGS_CACHE_TTL_MS = 120 * 1000;
let cachedLiveOfferings: PackageOffer[] | null = null;
let cachedLiveOfferingsAtMs = 0;

export const invalidateOfferingsCache = () => {
  cachedLiveOfferings = null;
  cachedLiveOfferingsAtMs = 0;
};

export const getOfferings = async (): Promise<PackageOffer[]> => {
  try {
    const ready = await initRevenueCat();
    if (!ready) return FALLBACK_OFFERINGS;
    const Purchases = require('react-native-purchases').default;
    const offerings = await Purchases.getOfferings();
    if (offerings.current && offerings.current.availablePackages.length > 0) {
      const currentOfferingId: string | undefined = offerings.current.identifier || undefined;
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

      const mappedOfferings: PackageOffer[] = pkgs.map((pkg: any) => {
        const prod = pkg?.product || {};
        const pkgOfferingId = pkg?.offeringIdentifier || currentOfferingId;
        let introPriceString: string | undefined;
        let introPrice: number | undefined;
        let introEligibility: IntroEligibilityState = 'unknown';
        let introOfferType: IntroOfferType = 'none';

        let resolvedPrice = typeof prod.price === 'number' ? prod.price : undefined;
        let resolvedPriceString = prod.priceString || `${prod.currencyCode} ${prod.price}`;

        if (Platform.OS === 'ios') {
          const ip = prod.introPrice;
          const hasIpObj = Boolean(ip && typeof ip === 'object' && typeof ip.price === 'number');
          const ipVal = hasIpObj ? Number(ip.price) : -1;
          const eligEntry = prod.identifier ? iosEligMap[prod.identifier] : undefined;
          const statusNum = typeof eligEntry?.status === 'number' ? eligEntry.status : undefined;
          // Evrensel A/B Teklif Motoru (Build 75):
          // ipVal === 0 -> Grup B (İlk Ay Ücretsiz / FREE_TRIAL)
          // ipVal > 0   -> Grup A (İlk Ay ₺49,99 / PAY_UP_FRONT)
          if (hasIpObj && ipVal >= 0) {
            const currSym = (prod.priceString || '').replace(/[0-9.,\s]+/g, '') || '₺';
            introOfferType = ipVal === 0 ? 'free_trial' : 'paid_intro';
            introPrice = ipVal;
            introPriceString = ipVal === 0
              ? ((ip.priceString && /\d/.test(String(ip.priceString))) ? ip.priceString : `${currSym}0`)
              : (ip.priceString || undefined);
            if (statusNum === 2) introEligibility = 'eligible';
            else if (statusNum === 1 || statusNum === 3) {
              introEligibility = 'ineligible';
              introOfferType = 'none';
            } else {
              introEligibility = 'unknown';
            }
          } else {
            introEligibility = 'ineligible';
            introOfferType = 'none';
          }
        } else {
          const gpIntro = extractAndroidIntroOption(prod, pkg?.identifier, pkgOfferingId);
          introPriceString = gpIntro.introPriceString;
          introPrice = gpIntro.introPrice;
          introEligibility = gpIntro.eligibility;
          introOfferType = gpIntro.introOfferType;
          // Google Play'de prod.price alanı defaultOption (0 veya 49.99) döndürdüğünde gerçek yinelenen baz fiyatı (149.99) koru
          if (typeof gpIntro.recurringPrice === 'number' && gpIntro.recurringPrice > 0) {
            resolvedPrice = gpIntro.recurringPrice;
          }
          if (gpIntro.recurringPriceString) {
            resolvedPriceString = gpIntro.recurringPriceString;
          }
        }

        return {
          identifier: pkg.identifier,
          offeringIdentifier: pkgOfferingId,
          productId: prod.identifier || undefined,
          packageType: pkg.packageType,
          priceString: resolvedPriceString,
          price: resolvedPrice,
          currencyCode: prod.currencyCode || undefined,
          introPriceString,
          introPrice,
          introEligibility,
          introOfferType,
          title: prod.title,
          description: prod.description,
          rawPackage: pkg,
        };
      });

      // Yalnızca gerçek mağaza paketi (rawPackage) içeren canlı yanıtları önbelleğe al (FALLBACK_OFFERINGS asla önbelleklenmez)
      if (mappedOfferings.some(o => Boolean(o.rawPackage))) {
        cachedLiveOfferings = mappedOfferings;
        cachedLiveOfferingsAtMs = Date.now();
      }
      return mappedOfferings;
    }
  } catch (err) {
    console.log('[RevenueCat] Offerings alınamadı, yedek görüntüleme listesi:', err);
  }
  return FALLBACK_OFFERINGS;
};

export const getCachedOrFetchOfferings = async (): Promise<PackageOffer[]> => {
  if (
    cachedLiveOfferings &&
    cachedLiveOfferings.length > 0 &&
    cachedLiveOfferings.some(o => Boolean(o.rawPackage)) &&
    Date.now() - cachedLiveOfferingsAtMs < OFFERINGS_CACHE_TTL_MS
  ) {
    return cachedLiveOfferings;
  }
  return getOfferings();
};

export const purchasePackage = async (packageId: string, rawPackage?: any): Promise<PurchaseResult> => {
  try {
    const ready = await initRevenueCat();
    const Purchases = require('react-native-purchases').default;

    // 1. Yol: RevenueCat rawPackage varsa (Android'de A/B grubuna ait uygun intro/trial option varsa onu seçerek) çağır
    if (rawPackage) {
      if (Platform.OS === 'android' && Purchases.purchaseSubscriptionOption && rawPackage?.product) {
        const gpIntro = extractAndroidIntroOption(
          rawPackage.product,
          rawPackage.identifier || packageId,
          rawPackage.offeringIdentifier
        );
        if (gpIntro.option) {
          try {
            const optRes = await Purchases.purchaseSubscriptionOption(gpIntro.option);
            const optInfo = optRes?.customerInfo;
            return {
              success: true,
              isActive: hasActiveEntitlement(optInfo),
              customerInfo: optInfo,
              transaction: optRes?.transaction || optRes?.storeTransaction,
            };
          } catch (optErr: any) {
            if (optErr?.userCancelled) {
              return { success: false, isActive: false, cancelled: true };
            }
            // Google Play'de ödeme tamamlanıp ağ/makbuz senkronunda hata oluşmuş olabilir — önce canlı hakkı kontrol et
            try {
              const postErrInfo = await Purchases.getCustomerInfo();
              if (hasActiveEntitlement(postErrInfo)) {
                return {
                  success: true,
                  isActive: true,
                  customerInfo: postErrInfo,
                };
              }
            } catch {}
            // Yalnızca pencere açılmadan önce oluşan seçenek/yapılandırma hatasıysa standart purchasePackage yedeğine düş
            const errCodeStr = String(optErr?.code || optErr?.readableErrorCode || '').toUpperCase();
            const isPreSheetOptionError =
              errCodeStr.includes('PRODUCT_NOT_AVAILABLE') ||
              errCodeStr.includes('DEVELOPER_ERROR') ||
              errCodeStr.includes('CONFIGURATION_ERROR') ||
              errCodeStr.includes('INVALID') ||
              errCodeStr === '4' ||
              errCodeStr === '5' ||
              !gpIntro.option?.id;
            if (!isPreSheetOptionError) {
              console.warn('[RevenueCat] purchaseSubscriptionOption hatası:', optErr);
              return {
                success: false,
                isActive: false,
                error: optErr?.code ? String(optErr.code) : 'purchase_failed',
              };
            }
            console.warn('[RevenueCat] purchaseSubscriptionOption ön-seçenek hatası, purchasePackage yedeğine geçiliyor:', optErr);
          }
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

    // 2. Yol: rawPackage yoksa (StoreKit / Google Play doğrudan çoklu ürün fallback'i - A/B SKU'ları dahil)
    const isIOS = Platform.OS === 'ios';
    const isYearly = packageId.toLowerCase().includes('year') || packageId.toLowerCase().includes('annual') || packageId.toLowerCase() === 'misil';
    const candidateProductIds = Array.from(new Set([
      packageId,
      ...(isIOS
        ? (isYearly
            ? ['misil_annual', '$rc_annual', 'com.levitas.misilbaby.annual']
            : ['misil_monthly', 'misil_monthly_trial', 'misil_monthly_free', '$rc_monthly', 'com.levitas.misilbaby.monthly'])
        : (isYearly
            ? ['misil', 'misil:misil', 'misil_annual', '$rc_annual', 'com.levitas.misilbaby.annual']
            : ['misilaylik', 'misilaylik:misilaylik', 'misilaylik_trial', 'misil_monthly', '$rc_monthly', 'com.levitas.misilbaby.monthly'])
      ),
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
