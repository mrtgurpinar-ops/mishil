const { withAndroidManifest } = require('@expo/config-plugins');

/**
 * Expo Config Plugin: withAndroidMetaAutoInit
 *
 * Apple Guideline 5.1.2(i) (ATT) nedeniyle `react-native-fbsdk-next` ana eklentisinde
 * `isAutoInitEnabled: false`, `autoLogAppEventsEnabled: false`, `advertiserIDCollectionEnabled: false`
 * tutularak iOS `Info.plist` tarafındaki çalışan/onaylanmış ATT akışı %100 korunur.
 *
 * YALNIZCA Android (`AndroidManifest.xml`) tarafında ise Meta SDK'nın soğuk başlangıçta (`Application.onCreate` /
 * `MainActivity.onResume`) `ActivityLifecycleTracker` ve Google Play `InstallReferrerUtil` kancalarını
 * kaçırmaması ve Meta Ads Manager'da Android `MOBILE_APP_INSTALL` olaylarının eksiksiz sayılması için
 * `com.facebook.sdk.AutoInitEnabled`, `AutoLogAppEventsEnabled` ve `AdvertiserIDCollectionEnabled`
 * meta-data değerlerini `true` olarak yazar.
 */
function setOrReplaceMetaData(mainApplication, name, value) {
  if (!mainApplication['meta-data']) {
    mainApplication['meta-data'] = [];
  }
  const existing = mainApplication['meta-data'].find(
    (item) => item && item.$ && item.$['android:name'] === name
  );
  if (existing) {
    existing.$['android:value'] = String(value);
  } else {
    mainApplication['meta-data'].push({
      $: {
        'android:name': name,
        'android:value': String(value),
      },
    });
  }
}

const withAndroidMetaAutoInit = (config) => {
  return withAndroidManifest(config, (cfg) => {
    const mainApp =
      cfg.modResults &&
      cfg.modResults.manifest &&
      Array.isArray(cfg.modResults.manifest.application) &&
      cfg.modResults.manifest.application[0];

    if (mainApp) {
      setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AutoInitEnabled', 'true');
      setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AutoLogAppEventsEnabled', 'true');
      setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AdvertiserIDCollectionEnabled', 'true');
    }
    return cfg;
  });
};

module.exports = withAndroidMetaAutoInit;
