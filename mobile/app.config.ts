import { ExpoConfig, ConfigContext } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Mışıl Baby',
  slug: 'misil-baby',
  scheme: 'misilbaby',
  version: '4.7.0',
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
  assetBundlePatterns: ['**/*'],
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'com.levitas.misilbaby',
    infoPlist: {
      NSMicrophoneUsageDescription: 'Mışıl Baby, bebeğinizin ağlama sesindeki akustik özellikleri analiz etmek için mikrofonunuza erişir. Sesler yalnızca yerel analiz amaçlı işlenir ve kaydedilmez.',
      UIBackgroundModes: ['audio']
    }
  },
  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#141B2E'
    },
    package: 'com.levitas.misilbaby',
    versionCode: 6,
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
          targetSdkVersion: 36,
          compileSdkVersion: 36
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
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://mishil-api-production.up.railway.app/api/v1',
    revenueCatApiKeyIos: process.env.EXPO_PUBLIC_REVENUECAT_IOS || 'appl_mock_key',
    revenueCatApiKeyAndroid: process.env.EXPO_PUBLIC_REVENUECAT_ANDROID || 'goog_mock_key'
  }
});
