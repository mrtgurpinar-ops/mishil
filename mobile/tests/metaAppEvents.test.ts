// @ts-nocheck
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

function createMetaHarness(overrides = {}) {
  const storageMap = new Map(Object.entries(overrides.initialStorage || {}));
  const platformOs = overrides.platformOs || 'ios';
  const trackingResponse = overrides.trackingResponse || { status: 'granted', granted: true };

  const calls = {
    setAdvertiserTrackingEnabled: [],
    setAdvertiserIDCollectionEnabled: [],
    setAutoLogAppEventsEnabled: [],
    initializeSDK: 0,
    fetchDeferredAppLink: 0,
    logEvent: [],
    logPurchase: [],
    flush: 0,
    aemEnable: 0,
    aemLogEvent: [],
    requestTrackingPermissions: 0,
  };

  const filePath = path.resolve(__dirname, '../features/analytics/metaAppEvents.ts');
  const source = fs.readFileSync(filePath, 'utf8');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  });

  const mod = { exports: {} };
  const asyncStorageMock = {
    getItem: async (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: async (k, v) => {
      storageMap.set(k, String(v));
    },
  };

  const customRequire = (id) => {
    if (id === 'react-native') {
      return {
        Platform: { OS: platformOs },
      };
    }
    if (id === '@react-native-async-storage/async-storage') {
      return { default: asyncStorageMock, __esModule: true, ...asyncStorageMock };
    }
    if (id === 'expo-tracking-transparency') {
      return {
        requestTrackingPermissionsAsync: async () => {
          calls.requestTrackingPermissions += 1;
          return trackingResponse;
        },
      };
    }
    if (id === 'react-native-fbsdk-next') {
      return {
        Settings: {
          setAdvertiserTrackingEnabled: async (val) => {
            calls.setAdvertiserTrackingEnabled.push(val);
            return true;
          },
          setAdvertiserIDCollectionEnabled: (val) => {
            calls.setAdvertiserIDCollectionEnabled.push(val);
          },
          setAutoLogAppEventsEnabled: (val) => {
            calls.setAutoLogAppEventsEnabled.push(val);
          },
          initializeSDK: () => {
            calls.initializeSDK += 1;
          },
        },
        AppEventsLogger: {
          logEvent: (...args) => {
            calls.logEvent.push(args);
          },
          logPurchase: (...args) => {
            calls.logPurchase.push(args);
          },
          flush: () => {
            calls.flush += 1;
          },
        },
        AppLink: {
          fetchDeferredAppLink: async () => {
            calls.fetchDeferredAppLink += 1;
            return null;
          },
        },
        AEMReporterIOS: {
          enable: () => {
            calls.aemEnable += 1;
          },
          logAEMEvent: (...args) => {
            calls.aemLogEvent.push(args);
          },
        },
      };
    }
    return require(id);
  };

  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', transpiled.outputText);
  fn(mod.exports, customRequire, mod, filePath, path.dirname(filePath));

  return {
    meta: mod.exports,
    storageMap,
    calls,
  };
}

describe('Meta App Events & SKAdNetwork Bridge', () => {
  test('1. iOS ATT izni verildiğinde (granted) IDFA takibini açar ve eşzamanlı çağrılarda tekil Promise paylaşır', async () => {
    const { meta, calls } = createMetaHarness({
      platformOs: 'ios',
      trackingResponse: { status: 'granted', granted: true },
    });

    const [res1, res2] = await Promise.all([
      meta.initMetaSdkAndActivateApp(),
      meta.initMetaSdkAndActivateApp(),
    ]);
    expect(res1).toEqual({ initialized: true, trackingGranted: true });
    expect(res2).toEqual({ initialized: true, trackingGranted: true });
    expect(calls.requestTrackingPermissions).toBe(1);
    expect(calls.setAdvertiserTrackingEnabled).toEqual([true]);
    expect(calls.setAdvertiserIDCollectionEnabled).toEqual([true]);
    expect(calls.setAutoLogAppEventsEnabled).toEqual([true]);
    expect(calls.initializeSDK).toBe(1);
    expect(calls.fetchDeferredAppLink).toBe(0);
    expect(calls.logEvent).toContainEqual(['fb_mobile_activate_app', { platform: 'ios' }]);
  });

  test('2. iOS ATT izni reddedildiğinde (denied) IDFA kapalı kalır ama SKAdNetwork/activate_app yine çalışır', async () => {
    const { meta, calls } = createMetaHarness({
      platformOs: 'ios',
      trackingResponse: { status: 'denied', granted: false },
    });

    const res = await meta.initMetaSdkAndActivateApp();
    expect(res.initialized).toBe(true);
    expect(res.trackingGranted).toBe(false);
    expect(calls.setAdvertiserTrackingEnabled).toEqual([false]);
    expect(calls.setAdvertiserIDCollectionEnabled).toEqual([false]);
    expect(calls.initializeSDK).toBe(1);
    expect(calls.logEvent).toContainEqual(['fb_mobile_activate_app', { platform: 'ios' }]);
  });

  test('3. İlk ay 49.99 TRY indirimli abonelik alındığında (unknown/eligible dahil) gerçek 49.99 TRY loglanır, ROAS çift sayılmaz ve eşzamanlı çağrılar tekilleştirilir', async () => {
    const { meta, calls } = createMetaHarness({ platformOs: 'ios' });

    const [first, concurrentDuplicate] = await Promise.all([
      meta.logMetaSubscriptionPurchase({
        plan: 'monthly',
        price: 149.99,
        introPrice: 49.99,
        introEligibility: 'unknown',
        currencyCode: 'TRY',
        productId: 'misil_monthly',
        transactionId: 'tx_intro_001',
      }),
      meta.logMetaSubscriptionPurchase({
        plan: 'monthly',
        price: 149.99,
        introPrice: 49.99,
        introEligibility: 'unknown',
        currencyCode: 'TRY',
        productId: 'misil_monthly',
        transactionId: 'tx_intro_001',
      }),
    ]);

    expect(first.logged).toBe(true);
    expect(first.amount).toBe(49.99);
    expect(first.isIntroOffer).toBe(true);
    expect(first.currency).toBe('TRY');
    expect(concurrentDuplicate.logged).toBe(false);
    expect(concurrentDuplicate.reason).toBe('duplicate_transaction');

    // Subscribe parasal valueToSum olmadan gönderilir, gelir yalnızca logPurchase ile 1 kez bildirilir
    expect(calls.logEvent.length).toBe(1);
    expect(calls.logEvent[0][0]).toBe('Subscribe');
    expect(calls.logEvent[0][1]).toMatchObject({
      fb_currency: 'TRY',
      fb_content_id: 'misil_monthly',
      is_intro_offer: 1,
      fb_order_id: 'tx_intro_001',
    });
    expect(calls.logPurchase.length).toBe(1);
    expect(calls.logPurchase[0][0]).toBe(49.99);
    expect(calls.logPurchase[0][1]).toBe('TRY');
  });

  test('4. Daha önce abonelik kullanmış (ineligible) kullanıcıda 49.99 değil 149.99 TRY baz fiyat loglanır', async () => {
    const { meta, calls } = createMetaHarness({ platformOs: 'ios' });

    const res = await meta.logMetaSubscriptionPurchase({
      plan: 'monthly',
      price: 149.99,
      introPrice: 49.99,
      introEligibility: 'ineligible',
      periodType: 'NORMAL',
      currencyCode: 'TRY',
      productId: 'misil_monthly',
      transactionId: 'tx_base_002',
    });

    expect(res.logged).toBe(true);
    expect(res.amount).toBe(149.99);
    expect(res.isIntroOffer).toBe(false);
    expect(res.isFreeTrial).toBe(false);
    expect(calls.logPurchase[0][0]).toBe(149.99);
  });

  test('4b. Grup B (İlk Ay Ücretsiz / free_trial / 0 TRY) satın alındığında sahte ROAS şişmesini önlemek için logPurchase yerine standart StartTrial olayı ateşlenir', async () => {
    const { meta, calls } = createMetaHarness({ platformOs: 'ios' });

    const res = await meta.logMetaSubscriptionPurchase({
      plan: 'monthly',
      price: 149.99,
      introPrice: 0,
      introEligibility: 'eligible',
      introOfferType: 'free_trial',
      periodType: 'TRIAL',
      currencyCode: 'TRY',
      productId: 'misil_monthly_trial',
      transactionId: 'tx_trial_001',
    });

    expect(res.logged).toBe(true);
    expect(res.amount).toBe(0);
    expect(res.isIntroOffer).toBe(true);
    expect(res.isFreeTrial).toBe(true);
    expect(calls.logPurchase.length).toBe(0);
    expect(calls.logEvent.length).toBe(1);
    expect(calls.logEvent[0][0]).toBe('StartTrial');
    expect(calls.logEvent[0][1]).toMatchObject({
      fb_currency: 'TRY',
      fb_content_id: 'misil_monthly_trial',
      is_intro_offer: 1,
      is_free_trial: 1,
      fb_order_id: 'tx_trial_001',
    });
  });

  test('5. Onboarding tamamlandığında fb_mobile_complete_registration olayı gönderilir', () => {
    const { meta, calls } = createMetaHarness({ platformOs: 'android' });
    const ok = meta.logMetaOnboardingCompleted();
    expect(ok).toBe(true);
    expect(calls.logEvent).toContainEqual([
      'fb_mobile_complete_registration',
      { fb_registration_method: 'onboarding_quiz' },
    ]);
  });

  test('6. Android AppState active dönüşlerinde 15s throttle içinde tekrar loglamaz, 15s sonrasında fb_mobile_activate_app sinyalini yeniler', async () => {
    const origNow = Date.now;
    let fakeNow = 1_000_000;
    Date.now = () => fakeNow;
    try {
      const { meta, calls } = createMetaHarness({ platformOs: 'android' });
      await meta.initMetaSdkAndActivateApp();
      expect(calls.initializeSDK).toBe(1);
      expect(calls.logEvent.length).toBe(1);

      // 5s sonra çağrıldığında throttle nedeniyle yeni activate_app atmaz
      fakeNow += 5_000;
      await meta.initMetaSdkAndActivateApp();
      expect(calls.initializeSDK).toBe(1);
      expect(calls.logEvent.length).toBe(1);

      // 16s sonra çağrıldığında SDK yeniden init edilmeden activate_app + flush yenilenir
      fakeNow += 11_000;
      await meta.initMetaSdkAndActivateApp();
      expect(calls.initializeSDK).toBe(1);
      expect(calls.fetchDeferredAppLink).toBe(1);
      expect(calls.logEvent.length).toBe(2);
      expect(calls.flush).toBe(2);
    } finally {
      Date.now = origNow;
    }
  });

  test('7. Expo Config Plugins: AndroidManifest içinde AutoInit/AutoLog/AdvertiserID true üretilirken, iOS Info.plist içinde ATT koruması (false) %100 korunur', async () => {
    const mobileRoot = path.resolve(__dirname, '..');
    const { getConfig } = require(path.join(mobileRoot, 'node_modules/@expo/config'));
    const androidBm = require(path.join(
      mobileRoot,
      'node_modules/@expo/config-plugins/build/plugins/withAndroidBaseMods'
    ));
    const iosBm = require(path.join(
      mobileRoot,
      'node_modules/@expo/config-plugins/build/plugins/withIosBaseMods'
    ));

    // 1) AndroidManifest.xml mod zinciri doğrulaması
    let { exp: androidExp } = getConfig(mobileRoot, {
      skipSDKVersionRequirement: true,
      isModdedConfig: true,
    });
    androidExp = androidBm.withAndroidBaseMods(androidExp, {
      introspect: true,
      saveToInternal: true,
      providers: {
        manifest: androidBm.getAndroidModFileProviders().manifest,
      },
    });
    const androidRes = await androidExp.mods.android.manifest({
      modRequest: {
        projectRoot: mobileRoot,
        platformProjectRoot: path.join(mobileRoot, 'android'),
        modName: 'manifest',
        platform: 'android',
        introspect: true,
      },
      ...androidExp,
    });
    const metaDataList = androidRes.modResults.manifest.application[0]['meta-data'] || [];
    const getMetaValue = (name) => {
      const entry = metaDataList.find((item) => item && item.$ && item.$['android:name'] === name);
      return entry ? entry.$['android:value'] : undefined;
    };

    expect(getMetaValue('com.facebook.sdk.AutoInitEnabled')).toBe('true');
    expect(getMetaValue('com.facebook.sdk.AutoLogAppEventsEnabled')).toBe('true');
    expect(getMetaValue('com.facebook.sdk.AdvertiserIDCollectionEnabled')).toBe('true');
    expect(getMetaValue('com.facebook.sdk.ApplicationId')).toBe('@string/facebook_app_id');
    expect(getMetaValue('com.facebook.sdk.ClientToken')).toBe('@string/facebook_client_token');

    // 2) iOS Info.plist mod zinciri doğrulaması (ATT öncesi false kalmalı)
    let { exp: iosExp } = getConfig(mobileRoot, {
      skipSDKVersionRequirement: true,
      isModdedConfig: true,
    });
    iosExp = iosBm.withIosBaseMods(iosExp, {
      introspect: true,
      saveToInternal: true,
      providers: {
        infoPlist: iosBm.getIosModFileProviders().infoPlist,
      },
    });
    const iosRes = await iosExp.mods.ios.infoPlist({
      modRequest: {
        projectRoot: mobileRoot,
        platformProjectRoot: path.join(mobileRoot, 'ios'),
        modName: 'infoPlist',
        platform: 'ios',
        introspect: true,
      },
      ...iosExp,
    });
    const plist = iosRes.modResults;
    expect(plist.FacebookAutoInitEnabled).toBe(false);
    expect(plist.FacebookAutoLogAppEventsEnabled).toBe(false);
    expect(plist.FacebookAdvertiserIDCollectionEnabled).toBe(false);
    expect(plist.FacebookAppID).toBe('1093539003520092');
  });
});
