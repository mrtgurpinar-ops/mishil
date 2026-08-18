import { Platform } from 'react-native';
import Constants from 'expo-constants';

export interface PackageOffer {
  identifier: string;
  packageType: 'WEEKLY' | 'MONTHLY' | 'ANNUAL' | 'LIFETIME';
  priceString: string;
  title: string;
  description: string;
}

export const MOCK_OFFERINGS: PackageOffer[] = [
  {
    identifier: '$rc_annual',
    packageType: 'ANNUAL',
    priceString: '₺699,99 / Yıl',
    title: 'Yıllık Premium Plan',
    description: '3 gün ücretsiz dene. İstediğin an tek tıkla iptal edebilirsin.',
  },
  {
    identifier: '$rc_weekly',
    packageType: 'WEEKLY',
    priceString: '₺49,99 / Hafta',
    title: 'Haftalık Plan',
    description: 'Kısa dönemli takip ve esnek kullanım için.',
  },
];

export const initRevenueCat = async (userId?: string) => {
  const apiKey =
    Platform.OS === 'ios'
      ? Constants.expoConfig?.extra?.revenueCatApiKeyIos
      : Constants.expoConfig?.extra?.revenueCatApiKeyAndroid;

  console.log(`[RevenueCat] Initialized in sandbox mode with API Key: ${apiKey?.slice(0, 8)}...`);
  return true;
};

export const purchasePackage = async (packageId: string) => {
  console.log(`[RevenueCat] Initiating purchase for package: ${packageId}`);
  // In production: await Purchases.purchasePackage(pkg);
  return { success: true, customerInfo: { activeSubscriptions: [packageId] } };
};
