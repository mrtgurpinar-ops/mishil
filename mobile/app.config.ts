import { ExpoConfig, ConfigContext } from 'expo/config';

// Uygulama sürümü tek yerden — hem iOS buildNumber hem Android versionCode ile hizalı
const APP_VERSION = '4.57.3';
const BUILD_NUMBER = 74;

// Resmi Meta (Facebook) App Events & iOS 14+ SKAdNetwork kimlikleri
const META_APP_ID = process.env.EXPO_PUBLIC_META_APP_ID || '1093539003520092';
const META_CLIENT_TOKEN = process.env.EXPO_PUBLIC_META_CLIENT_TOKEN || '0677cfcf38d59f7d215c61be841091f0';
const IOS_TRACKING_PERMISSION_TEXT =
  'Mışıl Baby, size ve bebeğinizin gelişimine daha uygun içerikler sunabilmek ve kampanya performansını ölçebilmek için bu izni kullanır.';


const IS_PRODUCTION = process.env.APP_ENV === 'production';
const RC_KEY_IOS = process.env.EXPO_PUBLIC_REVENUECAT_IOS || 'appl_YErlYWqQcbRzipLuFKFliryZXAX';
const RC_KEY_ANDROID = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID || 'goog_LCNeMzKcaNSPdZModiKqmLtygYk';

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
    appleTeamId: 'V6QVVU79GZ',
    bundleIdentifier: 'com.levitas.misilbaby',
    buildNumber: String(BUILD_NUMBER),
    infoPlist: {
      CFBundleDevelopmentRegion: 'tr',
      CFBundleLocalizations: ['tr', 'en', 'de'],
      NSMicrophoneUsageDescription: 'Mışıl Baby, bebeğinizin ağlama sesindeki akustik özellikleri analiz etmek için mikrofonunuza erişir. Sesler yalnızca yerel analiz amaçlı işlenir ve kaydedilmez.',
      NSUserTrackingUsageDescription: IOS_TRACKING_PERMISSION_TEXT,
      UIBackgroundModes: ['audio'],
      SKAdNetworkItems: [
        { SKAdNetworkIdentifier: 'v9wttpbfk9.skadnetwork' },
        { SKAdNetworkIdentifier: 'n38lu8286q.skadnetwork' }
      ],
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
      'VIBRATE',
      'FOREGROUND_SERVICE',
      'FOREGROUND_SERVICE_MEDIA_PLAYBACK',
      'POST_NOTIFICATIONS',
      'android.permission.POST_PROMOTED_NOTIFICATIONS',
      'com.google.android.gms.permission.AD_ID'
    ]
  },
  plugins: [
    'expo-router',
    './plugins/withAndroidMetaAutoInit',
    [
      'expo-tracking-transparency',
      {
        userTrackingPermission: IOS_TRACKING_PERMISSION_TEXT
      }
    ],
    [
      'react-native-fbsdk-next',
      {
        appID: META_APP_ID,
        clientToken: META_CLIENT_TOKEN,
        displayName: 'Mışıl Baby',
        scheme: `fb${META_APP_ID}`,
        // Apple Guideline 5.1.2(i) koruması: ATT izni çözümlenene kadar derleme zamanı otomatik başlatma ve toplama kapalıdır;
        // çalışma zamanında metaAppEvents.ts içinde ATT izni sonrasında güvenli şekilde başlatılır.
        advertiserIDCollectionEnabled: false,
        autoLogAppEventsEnabled: false,
        isAutoInitEnabled: false,
        iosUserTrackingPermission: IOS_TRACKING_PERMISSION_TEXT
      }
    ],
    [
      'expo-build-properties',
      {
        android: {
          // Google Play 2026 zorunlu asgari hedefi: API 36 (Android 16)
          minSdkVersion: 26,
          targetSdkVersion: 36,
          compileSdkVersion: 36,
          enableProguardInReleaseBuilds: true,
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
        microphonePermission: 'Mışıl Baby, bebeğinizin ağlama sesindeki akustik özellikleri analiz etmek için mikrofonunuza erişir. Sesler yalnızca yerel analiz amaçlı işlenir ve kaydedilmez.'
      }
    ],
    [
      'expo-notifications',
      {
        icon: './assets/notification-icon.png',
        color: '#E8A855'
      }
    ],
    './plugins/withMinDeploymentTarget',
    './plugins/withMishilLiveActivity'
  ],
  extra: {
    eas: {
      projectId: "8e739202-2503-4aad-a970-46e22010fddc",
      build: {
        experimental: {
          ios: {
            appExtensions: [
              {
                targetName: 'MishilLiveActivity',
                bundleIdentifier: 'com.levitas.misilbaby.LiveSleepWidget'
              }
            ]
          }
        }
      }
    },
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://mishil-production.up.railway.app/api/v1',
    revenueCatApiKeyIos: RC_KEY_IOS,
    revenueCatApiKeyAndroid: RC_KEY_ANDROID
  }
});
