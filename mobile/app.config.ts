import { ExpoConfig, ConfigContext } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Mishil',
  slug: 'mishil',
  scheme: 'mishil',
  version: '1.0.0',
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
    supportsTablet: true,
    bundleIdentifier: 'com.mishil.app',
    infoPlist: {
      NSMicrophoneUsageDescription: 'Mishil, bebeğinizin ağlama sesindeki akustik özellikleri analiz etmek için mikrofonunuza erişir. Sesler yalnızca analiz amaçlı işlenir.',
      UIBackgroundModes: ['audio']
    }
  },
  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#141B2E'
    },
    package: 'com.mishil.app',
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
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000/api/v1',
    revenueCatApiKeyIos: process.env.EXPO_PUBLIC_REVENUECAT_IOS || 'appl_mock_key',
    revenueCatApiKeyAndroid: process.env.EXPO_PUBLIC_REVENUECAT_ANDROID || 'goog_mock_key'
  }
});
