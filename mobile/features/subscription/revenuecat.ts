import { Platform } from 'react-native';
import Constants from 'expo-constants';

export interface PackageOffer {
  identifier: string;
  packageType: 'WEEKLY' | 'MONTHLY' | 'ANNUAL' | 'LIFETIME';
  priceString: string;
  title: string;
  description: string;
  rawPackage?: any;
}

export interface PurchaseResult {
  success: boolean;      // akış hatasız tamamlandı mı
  isActive: boolean;     // kullanıcının GERÇEKTEN aktif bir hak sahibi olup olmadığı
  cancelled?: boolean;
  error?: string;
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
    title: '🌙 Mışıl Baby Aylık VIP (Önerilen)',
    description: '7 Gün Ücretsiz Deneme • Sonrasında Aylık ₺149,99 • İstediğiniz an iptal edin.',
  },
  {
    identifier: '$rc_annual',
    packageType: 'ANNUAL',
    priceString: '₺599,99 / Yıl',
    title: '👑 Mışıl Baby Yıllık VIP (Tasarruflu)',
    description: '7 Gün Ücretsiz Deneme • Aylık ₺49,99 karşılığı • %67 Tasarruf.',
  },
];

let isConfigured = false;
let isRealKey = false;

const getApiKey = () =>
  Platform.OS === 'ios'
    ? Constants.expoConfig?.extra?.revenueCatApiKeyIos
    : Constants.expoConfig?.extra?.revenueCatApiKeyAndroid;

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
    await Purchases.configure({ apiKey, appUserID: userId });
    isConfigured = true;
    isRealKey = true;
    console.log('[RevenueCat] Google Play / App Store ile yapılandırıldı.');
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
  const nonSubs = customerInfo.nonSubscriptionTransactions?.length || 0;
  return activeEntitlements.length > 0 || activeSubs.length > 0 || nonSubs > 0;
};

export const getOfferings = async (): Promise<PackageOffer[]> => {
  try {
    const ready = await initRevenueCat();
    if (!ready) return FALLBACK_OFFERINGS;
    const Purchases = require('react-native-purchases').default;
    const offerings = await Purchases.getOfferings();
    if (offerings.current && offerings.current.availablePackages.length > 0) {
      return offerings.current.availablePackages.map((pkg: any) => ({
        identifier: pkg.identifier,
        packageType: pkg.packageType,
        priceString: pkg.product.priceString || `${pkg.product.currencyCode} ${pkg.product.price}`,
        title: pkg.product.title,
        description: pkg.product.description,
        rawPackage: pkg,
      }));
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

    // 1. Yol: RevenueCat rawPackage varsa doğrudan purchasePackage çağır
    if (rawPackage) {
      const { customerInfo } = await Purchases.purchasePackage(rawPackage);
      return { success: true, isActive: hasActiveEntitlement(customerInfo) };
    }

    // 2. Yol: rawPackage yoksa (StoreKit / Google Play doğrudan çoklu ürün fallback'i)
    const isYearly = packageId.toLowerCase().includes('year') || packageId.toLowerCase().includes('annual');
    const candidateProductIds = isYearly
      ? ['yearly', 'misil_annual', 'misil_yearly', 'misil_baby_annual', '$rc_annual', 'annual']
      : ['monthly', 'misil_monthly', 'misil_baby_monthly', '$rc_monthly', 'misil_sub_monthly'];

    if (ready && Purchases.getProducts) {
      try {
        console.log('[RevenueCat] Mağazada aranacak olası ürün ID\'leri:', candidateProductIds);
        const products = await Purchases.getProducts(candidateProductIds);
        if (products && products.length > 0) {
          console.log('[RevenueCat] Eşleşen mağaza ürünü bulundu:', products[0].identifier);
          const { customerInfo } = await Purchases.purchaseStoreProduct(products[0]);
          return { success: true, isActive: hasActiveEntitlement(customerInfo) };
        } else {
          console.warn('[RevenueCat] Aday ID\'lerin hiçbiri mağazada bulunamadı:', candidateProductIds);
        }
      } catch (storeErr: any) {
        if (storeErr?.userCancelled) return { success: false, isActive: false, cancelled: true };
        console.warn('[RevenueCat] purchaseStoreProduct hatası:', storeErr);
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
    console.log('[RevenueCat] Satın alma hatası:', err);
    return { success: false, isActive: false, error: String(err?.message || err) };
  }
};

export const restorePurchases = async (): Promise<PurchaseResult> => {
  try {
    const ready = await initRevenueCat();
    if (!ready) return { success: false, isActive: false, error: 'not_configured' };
    const Purchases = require('react-native-purchases').default;
    const customerInfo = await Purchases.restorePurchases();
    // restore "başarılı" olsa bile hak yoksa Pro AÇILMAMALI
    return { success: true, isActive: hasActiveEntitlement(customerInfo) };
  } catch (err) {
    console.log('[RevenueCat] Geri yükleme hatası:', err);
    return { success: false, isActive: false, error: String(err) };
  }
};
