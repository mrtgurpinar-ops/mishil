const { withBaseMod } = require('@expo/config-plugins/build/plugins/withMod');

/**
 * Expo Config Plugin: withAndroidMetaAutoInit
 *
 * Apple Guideline 5.1.2(i) (ATT) nedeniyle `react-native-fbsdk-next` ana eklentisinde
 * `isAutoInitEnabled: false`, `autoLogAppEventsEnabled: false`, `advertiserIDCollectionEnabled: false`
 * tutularak iOS `Info.plist` tarafındaki çalışan/onaylanmış ATT akışı %100 korunur.
 *
 * `@expo/config-plugins` `withMod` zinciri LIFO (`action -> nextMod`) çalıştığı için,
 * bu eklenti hem `app.config.ts` içinde `react-native-fbsdk-next` öncesine konumlandırılır
 * hem de `withBaseMod` üzerinde hem `nextMod` öncesinde hem de `await nextMod(...)` dönüşünde
 * (post-hook olarak) `AndroidManifest.xml` içerisindeki Meta SDK bayraklarını `'true'` yapar.
 * Böylece `plugins` dizisindeki sıra ne olursa olsun `withFacebookManifest` tarafından
 * `'false'` ile ezilmesi imkânsız hale getirilir.
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

function applyAndroidMetaAutoInitFlags(modResults) {
  const mainApp =
    modResults &&
    modResults.manifest &&
    Array.isArray(modResults.manifest.application) &&
    modResults.manifest.application[0];

  if (mainApp) {
    setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AutoInitEnabled', 'true');
    setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AutoLogAppEventsEnabled', 'true');
    setOrReplaceMetaData(mainApp, 'com.facebook.sdk.AdvertiserIDCollectionEnabled', 'true');
  }
}

const withAndroidMetaAutoInit = (config) => {
  return withBaseMod(config, {
    platform: 'android',
    mod: 'manifest',
    isProvider: false,
    async action({ modRequest: { nextMod, ...modRequest }, modResults, ...cfg }) {
      applyAndroidMetaAutoInitFlags(modResults);
      const nextResults = await nextMod({
        modRequest,
        modResults,
        ...cfg,
      });
      if (nextResults && nextResults.modResults) {
        applyAndroidMetaAutoInitFlags(nextResults.modResults);
      }
      return nextResults;
    },
  });
};

module.exports = withAndroidMetaAutoInit;
