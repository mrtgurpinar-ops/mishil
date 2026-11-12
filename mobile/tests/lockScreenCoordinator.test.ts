// @ts-nocheck
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

function loadTs(relativePath, mocks = {}) {
  const filePath = path.resolve(__dirname, '..', relativePath);
  const source = fs.readFileSync(filePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const mod = { exports: {} };
  const customRequire = (id) => Object.prototype.hasOwnProperty.call(mocks, id) ? mocks[id] : require(id);
  new Function('exports', 'require', 'module', '__filename', '__dirname', output)(
    mod.exports, customRequire, mod, filePath, path.dirname(filePath),
  );
  return mod.exports;
}

describe('native audio player', () => {
  afterEach(() => jest.resetModules());

  function loadAudioPlayer(nativeAvailable) {
    const playbackListeners = [];
    let quotaState = {
      onboardedOnce: true,
      firstSpotUsed: false,
      freeSoundUsed: false,
      freeSoundElapsedMs: 0,
      freeCryUsed: false,
      freeDadiUsed: false,
    };
    let livePreviewElapsedMs = 0;
    let livePreviewExhausted = false;
    const native = {
      isNativeLockScreenAvailable: jest.fn(() => nativeAvailable),
      addPlaybackListener: jest.fn((listener) => { playbackListeners.push(listener); return { remove: jest.fn() }; }),
      playAudio: jest.fn(async () => true), stopAudio: jest.fn(async () => {}),
      setAudioVolume: jest.fn(async () => {}),
      getLockScreenState: jest.fn(async () => ({
        audioPlaying: true,
        audioPaused: false,
        audioId: 'active',
        previewElapsedMs: livePreviewElapsedMs,
        previewExhausted: livePreviewExhausted,
        sleepActive: false,
        sleepStartEpochMs: null,
      })),
    };
    const sound = { stopAsync: jest.fn(), unloadAsync: jest.fn(), setOnPlaybackStatusUpdate: jest.fn() };
    const audio = {
      setAudioModeAsync: jest.fn(async () => {}),
      Sound: { createAsync: jest.fn(async () => ({ sound })) },
    };
    const getDeviceQuotas = jest.fn(async () => ({ ...quotaState }));
    const mergeDeviceQuotas = jest.fn(async (patch) => {
      quotaState = {
        ...quotaState,
        ...patch,
        freeSoundElapsedMs: Math.max(quotaState.freeSoundElapsedMs, patch.freeSoundElapsedMs || 0),
        freeSoundUsed: Boolean(quotaState.freeSoundUsed || patch.freeSoundUsed),
      };
      return { ...quotaState };
    });
    const player = loadTs('features/audio/nativeAudioPlayer.ts', {
      'expo-av': { Audio: audio, InterruptionModeIOS: {}, InterruptionModeAndroid: {} },
      '../../modules/mishil-lockscreen/src': native,
      '../../lib/storage': { storage: { getDeviceQuotas, mergeDeviceQuotas } },
    });
    return {
      player,
      native,
      audio,
      sound,
      getDeviceQuotas,
      mergeDeviceQuotas,
      playbackListeners,
      setLivePreview: (ms, exhausted = false) => {
        livePreviewElapsedMs = ms;
        livePreviewExhausted = exhausted;
      },
    };
  }

  it('passes metadata, handles exhausted quota, and forwards remote controls', async () => {
    const ctx = loadAudioPlayer(true);
    const onState = jest.fn();
    await ctx.player.playSound('lullaby', 'https://audio.test/a.mp3', onState, {
      title: 'Ninni', subtitle: 'Uyku sesi', isVip: false, previewBudgetMs: 60000,
    });
    expect(ctx.native.playAudio).toHaveBeenCalledWith(expect.objectContaining({
      id: 'lullaby', title: 'Ninni', subtitle: 'Uyku sesi', isVip: false, previewBudgetMs: 60000,
    }));
    const listener = ctx.playbackListeners[0];
    listener({ playing: false, id: null, reason: 'preview_quota_exhausted' });
    expect(ctx.mergeDeviceQuotas).toHaveBeenCalledWith({ freeSoundUsed: true, freeSoundElapsedMs: 60000 });
    expect(onState).toHaveBeenLastCalledWith({
      playing: false,
      id: null,
      reason: 'preview_quota_exhausted',
      previewElapsedMs: 60000,
    });
    for (const reason of ['remote_pause', 'remote_play', 'remote_stop']) {
      listener({ playing: reason === 'remote_play', id: reason === 'remote_play' ? 'lullaby' : null, reason });
      expect(onState).toHaveBeenLastCalledWith(expect.objectContaining({ reason }));
    }
  });

  it('persists partial elapsed preview time on early stop and clamps subsequent session budget', async () => {
    const ctx = loadAudioPlayer(true);
    const onState = jest.fn();
    await ctx.player.playSound('womb', 'https://audio.test/womb.mp3', onState, {
      title: 'Anne Karnı', isVip: false, previewBudgetMs: 60000,
    });
    const listener = ctx.playbackListeners[0];
    listener({ playing: false, id: 'womb', reason: 'remote_stop', previewElapsedMs: 25000 });
    expect(ctx.mergeDeviceQuotas).toHaveBeenCalledWith({
      freeSoundUsed: false,
      freeSoundElapsedMs: 25000,
    });

    // İkinci başlatmada WebView yanlışlıkla 60000 gönderse bile native kalan bütçeyi 35000 ms ile sınırlar
    await ctx.player.playSound('pink', 'https://audio.test/pink.mp3', onState, {
      title: 'Pembe Gürültü', isVip: false, previewBudgetMs: 60000,
    });
    expect(ctx.native.playAudio).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'pink', isVip: false, previewBudgetMs: 35000,
    }));
  });

  it('deducts live elapsed time on direct track switch without double-counting and blocks stale storage races', async () => {
    const ctx = loadAudioPlayer(true);
    const onState = jest.fn();

    await ctx.player.playSound('womb', 'https://audio.test/womb.mp3', onState, {
      title: 'Anne Karnı', isVip: false, previewBudgetMs: 60000,
    });

    // Kullanıcı stop demeden doğrudan başka bir sese geçiyor (22 sn dinledikten sonra)
    ctx.setLivePreview(22000, false);
    ctx.native.playAudio.mockImplementationOnce(async () => {
      // Native katman da geçiş sırasında track_switch olayı fırlatır
      ctx.playbackListeners[0]({ playing: false, id: 'womb', reason: 'track_switch', previewElapsedMs: 22000 });
      return true;
    });

    await ctx.player.playSound('rain', 'https://audio.test/rain.mp3', onState, {
      title: 'Yağmur', isVip: false, previewBudgetMs: 60000,
    });

    expect(ctx.native.playAudio).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'rain', isVip: false, previewBudgetMs: 38000,
    }));
    // UI'a sahte ara stop düşmemeli
    expect(onState).not.toHaveBeenCalledWith(expect.objectContaining({ reason: 'track_switch' }));

    // İkinci parça da 18 sn dinlenip durdurulduğunda toplam 40 sn olmalı (çift sayım olmamalı)
    ctx.setLivePreview(0, false);
    ctx.getDeviceQuotas.mockImplementationOnce(async () => ({
      onboardedOnce: true,
      firstSpotUsed: false,
      freeSoundUsed: false,
      freeSoundElapsedMs: 0, // Asenkron depolama geriden gelse bile bellek yüksek su izi (40 sn) korumalı
      freeCryUsed: false,
      freeDadiUsed: false,
    }));
    ctx.playbackListeners[0]({ playing: false, id: 'rain', reason: 'remote_stop', previewElapsedMs: 18000 });

    await ctx.player.playSound('waves', 'https://audio.test/waves.mp3', onState, {
      title: 'Dalga', isVip: false, previewBudgetMs: 60000,
    });
    expect(ctx.native.playAudio).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'waves', isVip: false, previewBudgetMs: 20000,
    }));
  });

  it('serializes unawaited rapid stopSound + playSound + slow async quota storage without leaking budget or double-counting', async () => {
    const ctx = loadAudioPlayer(true);
    const onState = jest.fn();
    const callOrder = [];

    await ctx.player.playSound('track1', 'https://audio.test/1.mp3', onState, {
      title: 'Parça 1', isVip: false, previewBudgetMs: 60000,
    });

    // 27 sn dinlendikten sonra kullanıcı arka arkaya (await etmeden) Durdur + Yeni Ses Başlat'a basar;
    // hem native stopAudio hem de mergeDeviceQuotas gecikmeli tamamlanır.
    ctx.setLivePreview(27000, false);
    ctx.mergeDeviceQuotas.mockImplementationOnce(
      (patch) =>
        new Promise((resolve) => {
          setTimeout(() => {
            callOrder.push('quota_persisted');
            resolve({ freeSoundUsed: Boolean(patch.freeSoundUsed), freeSoundElapsedMs: patch.freeSoundElapsedMs || 0 });
          }, 25);
        })
    );
    ctx.native.stopAudio.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            callOrder.push('native_stopped');
            ctx.playbackListeners[0]({ playing: false, id: 'track1', reason: 'user', previewElapsedMs: 27000 });
            ctx.setLivePreview(0, false);
            resolve();
          }, 15);
        })
    );
    ctx.native.playAudio.mockImplementationOnce(async (opts) => {
      callOrder.push(`native_play_${opts.id}_${opts.previewBudgetMs}`);
      return true;
    });

    // WebView köprüsündeki gibi await etmeden peş peşe ateşle
    const stopPromise = ctx.player.stopSound(onState, 'user');
    const playPromise = ctx.player.playSound('track2', 'https://audio.test/2.mp3', onState, {
      title: 'Parça 2', isVip: false, previewBudgetMs: 60000,
    });

    await Promise.all([stopPromise, playPromise]);

    // Sıralama kilidi sayesinde önce stop ve kota yazımı biter, sonra track2 tam 33000 ms kalan bütçeyle başlar (çift sayım yok)
    expect(callOrder[0]).toBe('native_stopped');
    expect(callOrder).toContain('quota_persisted');
    expect(callOrder[callOrder.length - 1]).toBe('native_play_track2_33000');
    expect(ctx.native.playAudio).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'track2', isVip: false, previewBudgetMs: 33000,
    }));
    expect(onState).toHaveBeenLastCalledWith({ playing: true, id: 'track2' });

    // Eşzamanlı çift playSound çağrısında (A ve B aynı anda) eski çağrı (A) generation kilidiyle iptal edilir, yalnızca son seçim (B) çalar
    const rapidA = ctx.player.playSound('staleA', 'https://audio.test/a.mp3', onState, {
      title: 'Eski Seçim', isVip: false, previewBudgetMs: 60000,
    });
    const rapidB = ctx.player.playSound('winnerB', 'https://audio.test/b.mp3', onState, {
      title: 'Son Seçim', isVip: false, previewBudgetMs: 60000,
    });
    await Promise.all([rapidA, rapidB]);

    expect(ctx.native.playAudio).not.toHaveBeenCalledWith(expect.objectContaining({ id: 'staleA' }));
    expect(ctx.native.playAudio).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'winnerB', isVip: false, previewBudgetMs: 33000,
    }));
  });

  it('retains expo-av playback fallback when the native module is unavailable', async () => {
    const ctx = loadAudioPlayer(false);
    const onState = jest.fn();
    await ctx.player.playSound('classic', 'https://audio.test/a.mp3', onState);
    expect(ctx.audio.Sound.createAsync).toHaveBeenCalledWith(
      { uri: 'https://audio.test/a.mp3' }, expect.objectContaining({ shouldPlay: true, isLooping: true }),
    );
    expect(ctx.native.playAudio).not.toHaveBeenCalled();
    expect(onState).toHaveBeenCalledWith({ playing: true, id: 'classic' });
  });
});

describe('native live sleep coordinator', () => {
  afterEach(() => { jest.useRealTimers(); jest.resetModules(); });

  function setup(initialValue = null, systemSleepActive = true) {
    let stored = initialValue;
    const asyncStorage = {
      getItem: jest.fn(async () => stored),
      setItem: jest.fn(async (_key, value) => { stored = value; }),
      removeItem: jest.fn(async () => { stored = null; }),
    };
    const native = {
      isNativeLockScreenAvailable: jest.fn(() => true),
      startLiveSleep: jest.fn(async () => true), updateLiveSleep: jest.fn(async () => true),
      stopLiveSleep: jest.fn(async () => {}),
      getLockScreenState: jest.fn(async () => ({
        audioPlaying: false,
        audioPaused: false,
        audioId: null,
        previewElapsedMs: 0,
        previewExhausted: false,
        sleepActive: systemSleepActive,
        sleepStartEpochMs: systemSleepActive ? 100 : null,
      })),
    };
    const coordinator = loadTs('features/sleep/nativeLiveSleep.ts', {
      '@react-native-async-storage/async-storage': { __esModule: true, default: asyncStorage },
      'expo-notifications': {}, 'react-native': { Platform: { OS: 'ios', Version: 18 } },
      '../../modules/mishil-lockscreen/src': native,
    });
    return { coordinator, native, asyncStorage, get stored() { return stored; } };
  }

  it('starts, updates a retroactive start time, and clears persisted state when stopped', async () => {
    const ctx = setup();
    await ctx.coordinator.startNativeLiveSleep({ startEpochMs: 100, sleepLabel: 'Uyku', subtitle: 'Sessiz', lang: 'tr' });
    expect(JSON.parse(ctx.stored)).toEqual(expect.objectContaining({ active: true, startEpochMs: 100 }));
    await ctx.coordinator.updateNativeLiveSleep({ startEpochMs: 50, sleepLabel: 'Güncellendi' });
    expect(ctx.native.updateLiveSleep).toHaveBeenCalledWith({ startEpochMs: 50, sleepLabel: 'Güncellendi' });
    await ctx.coordinator.stopNativeLiveSleep();
    expect(ctx.asyncStorage.removeItem).toHaveBeenCalledWith('@mishil_live_sleep_native');
    expect(ctx.stored).toBeNull();
    expect(ctx.native.stopLiveSleep).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['stale active record', { active: true, startEpochMs: 1 }, true],
    ['inactive record', { active: false, startEpochMs: Date.now() }, true],
    ['fresh active record', { active: true, startEpochMs: Date.now() }, false],
  ])('reconciles %s correctly', async (_name, state, shouldStop) => {
    jest.useFakeTimers().setSystemTime(new Date('2026-11-12T12:00:00Z'));
    const timestampedState = { ...state, startEpochMs: state.startEpochMs === 1 ? Date.now() - 17 * 3600000 : Date.now() };
    const ctx = setup(JSON.stringify(timestampedState));
    await ctx.coordinator.reconcileNativeLiveSleepOnLaunch();
    expect(ctx.native.stopLiveSleep).toHaveBeenCalledTimes(shouldStop ? 1 : 0);
    if (state.active && shouldStop) expect(ctx.asyncStorage.removeItem).toHaveBeenCalledWith('@mishil_live_sleep_native');
    else expect(ctx.asyncStorage.removeItem).not.toHaveBeenCalled();
  });

  it('re-creates Live Activity automatically when iOS 8h limit drops the system activity during update or foreground reconcile', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-11-12T06:30:00Z'));
    const startEpochMs = Date.now() - 8.5 * 3600000; // 8.5 saatlik gece uykusu (<16 saat)
    const ctx = setup(
      JSON.stringify({
        active: true,
        startEpochMs,
        sleepLabel: 'Bebeğiniz uyuyor',
        subtitle: 'Mışıl Baby • Canlı Uyku',
        lang: 'tr',
      }),
      false // iOS ActivityKit 8 saat sonunda sistem aktivitesini düşürmüş
    );

    await ctx.coordinator.reconcileNativeLiveSleepOnLaunch();
    expect(ctx.native.startLiveSleep).toHaveBeenCalledWith(
      expect.objectContaining({ startEpochMs, sleepLabel: 'Bebeğiniz uyuyor', lang: 'tr' })
    );

    // updateLiveSleep false dönerse de startLiveSleep ile kendi kendini onarır
    ctx.native.startLiveSleep.mockClear();
    ctx.native.updateLiveSleep.mockResolvedValueOnce(false);
    await ctx.coordinator.updateNativeLiveSleep({ startEpochMs: startEpochMs - 900000, sleepLabel: 'Gece Uykusu' });
    expect(ctx.native.startLiveSleep).toHaveBeenCalledWith(
      expect.objectContaining({ startEpochMs: startEpochMs - 900000, sleepLabel: 'Gece Uykusu' })
    );
  });
});

describe('Live Activity config plugin', () => {
  afterEach(() => jest.resetModules());

  it('enables Live Activities and adds one correctly configured extension target idempotently', () => {
    const pluginCalls = [];
    const configPlugins = {
      withInfoPlist: (config, action) => { pluginCalls.push(() => { config.modResults = action(config).modResults; }); return config; },
      withDangerousMod: (config) => config,
      withXcodeProject: (config, action) => { pluginCalls.push(() => { config.modResults = action(config).modResults; }); return config; },
    };
    jest.doMock('@expo/config-plugins', () => configPlugins);
    const plugin = require('../plugins/withMishilLiveActivity.js');
    const target = { uuid: 'TARGET', buildConfigurationList: 'CONFIG_LIST' };
    const buildConfigurations = { CONFIG: { buildSettings: { PRODUCT_NAME: '"MishilLiveActivity"' } } };
    const project = {
      hash: { project: { objects: {} } },
      pbxNativeTargetSection: () => project.targets,
      targets: {},
      addPbxGroup: jest.fn(() => ({ uuid: 'GROUP' })),
      getFirstProject: jest.fn(() => ({ firstProject: { mainGroup: 'MAIN' } })),
      addToPbxGroup: jest.fn(),
      addTarget: jest.fn((name, type, subfolder, bundleId) => {
        project.targets.TARGET = { name, type, productType: 'app_extension' };
        return { ...target, bundleId };
      }),
      addBuildPhase: jest.fn(),
      pbxXCBuildConfigurationSection: () => buildConfigurations,
    };
    const config = { version: '4.51.0', ios: { bundleIdentifier: 'com.test.app', buildNumber: '70' }, modResults: { }, };
    plugin(config);
    config.modResults = { NSSupportsLiveActivities: false };
    pluginCalls[0]();
    expect(config.modResults.NSSupportsLiveActivities).toBe(true);
    config.modResults = project;
    pluginCalls[1]();
    pluginCalls[1]();
    expect(project.addTarget).toHaveBeenCalledTimes(1);
    expect(project.targets.TARGET).toEqual(expect.objectContaining({ name: 'MishilLiveActivity', type: 'app_extension' }));
    const settings = buildConfigurations.CONFIG.buildSettings;
    expect(settings.IPHONEOS_DEPLOYMENT_TARGET).toBe('16.2');
    expect(settings.SWIFT_VERSION).toBe('5.0');
  });
});
