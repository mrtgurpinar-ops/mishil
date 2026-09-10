import { ExpoConfig, ConfigContext } from 'expo/config';

// Uygulama sürümü tek yerden — hem iOS buildNumber hem Android versionCode ile hizalı
const APP_VERSION = '4.20.0';
const BUILD_NUMBER = 32;

const IS_PRODUCTION = process.env.APP_ENV === 'production';
const RC_KEY_IOS = process.env.EXPO_PUBLIC_REVENUECAT_IOS || 'appl_mock_key';
const RC_KEY_ANDROID = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID || 'goog_mock_key';

// Yayın derlemesi (eas.json production profili APP_ENV=production verir) mock RevenueCat
// anahtarıyla ÜRETİLEMEZ — platforma göre aktif anahtar doğrulanır.
const isAndroidBuild = process.env.EAS_BUILD_PLATFORM === 'android';
const isIosBuild = process.env.EAS_BUILD_PLATFORM === 'ios';

if (IS_PRODUCTION) {
  if ((isAndroidBuild || !isIosBuild) && RC_KEY_ANDROID.includes('mock_key')) {
    throw new Error('[app.config] Android production derlemesi için EXPO_PUBLIC_REVENUECAT_ANDROID tanımlanmalı.');
  }
  if (isIosBuild && RC_KEY_IOS.includes('mock_key')) {
    throw new Error('[app.config] iOS production derlemesi için EXPO_PUBLIC_REVENUECAT_IOS tanımlanmalı.');
  }
}

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Mışıl Baby',
  slug: 'misil-baby',
  scheme: 'misilbaby',
  version: APP_VERSION,
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#141B2E'
  },
  web: {
    bundler: 'metro',
    output: 'static'
  },
  assetBundlePatterns: ['**/*', 'public/**'],
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'com.levitas.misilbaby',
    buildNumber: String(BUILD_NUMBER),
    infoPlist: {
      NSMicrophoneUsageDescription: 'Mışıl Baby, bebeğinizin ağlama sesindeki akustik özellikleri analiz etmek için mikrofonunuza erişir. Sesler yalnızca yerel analiz amaçlı işlenir ve kaydedilmez.',
      UIBackgroundModes: ['audio'],
      // İhracat uyumluluğu: standart HTTPS dışında şifreleme kullanılmıyor →
      // her TestFlight/App Store yüklemesinde çıkan soruyu otomatik geçer
      ITSAppUsesNonExemptEncryption: false
    }
  },
  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#141B2E'
    },
    package: 'com.levitas.misilbaby',
    versionCode: BUILD_NUMBER,
    permissions: [
      'RECORD_AUDIO',
      'WAKE_LOCK',
      'RECEIVE_BOOT_COMPLETED',
      'VIBRATE'
    ]
  },
  plugins: [
    'expo-router',
    [
      'expo-build-properties',
      {
        android: {
          // Google Play 2026 zorunlu asgari hedefi: API 36 (Android 16)
          minSdkVersion: 26,
          targetSdkVersion: 36,
          compileSdkVersion: 36,
          extraGradleProperties: {
            'android.suppressUnsupportedCompileSdk': '36'
          }
        },
        ios: {
          // Apple App Store ITMS-90068 uyumu: asgari iOS 15.0+ zorunluluğu
          deploymentTarget: '15.1'
        }
      }
    ],
    [
      'expo-av',
      {
        microphonePermission: 'Mishil, bebeğinizin ağlama sesini değerlendirmek için mikrofon erişimine ihtiyaç duyar.'
      }
    ],
    [
      'expo-notifications',
      {
        icon: './assets/notification-icon.png',
        color: '#E8A855'
      }
    ]
  ],
  extra: {
    eas: {
      projectId: "8e739202-2503-4aad-a970-46e22010fddc"
    },
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://mishil-production.up.railway.app/api/v1',
    revenueCatApiKeyIos: RC_KEY_IOS,
    revenueCatApiKeyAndroid: RC_KEY_ANDROID
  }
});
