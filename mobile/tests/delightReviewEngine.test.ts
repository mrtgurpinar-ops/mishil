// @ts-nocheck
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function createDelightEngineSandbox(opts = {}) {
  const htmlPath = path.resolve(__dirname, '../../public/app.html');
  const html = fs.readFileSync(htmlPath, 'utf8').replace(/\r\n/g, '\n');

  const startMarker = '// RESMİ UYGULAMA İÇİ YILDIZ KUTUSU (expo-store-review) & 5 MUTLU-AN MOTORU';
  const endMarker = 'window.dismissRatingSheet = dismissRatingSheet;';
  const startIdx = html.indexOf(startMarker);
  const endIdx = html.indexOf(endMarker, startIdx);
  if (startIdx === -1 || endIdx === -1) {
    throw new Error('Could not locate Delight Review Engine block in public/app.html');
  }
  const blockCode = html.slice(startIdx, endIdx + endMarker.length);

  const storage = new Map(Object.entries(opts.initialStorage || {}));
  const postedMessages = [];
  const activeOverlays = new Set(opts.activeOverlays || []);

  const sandbox = {
    Date,
    Math,
    JSON,
    Number,
    String,
    Boolean,
    parseInt,
    parseFloat,
    setTimeout,
    clearTimeout,
    console: { warn: () => {}, log: () => {} },
    isPurchaseInFlight: !!opts.isPurchaseInFlight,
    currentTrackId: opts.currentTrackId || null,
    isSleeping: !!opts.isSleeping,
    WEB_APP_META: { version: '4.48.3' },
    isEn: () => false,
    getStoreName: () => 'App Store',
    getAppPlatform: () => 'ios',
    getApiBaseUrl: () => 'https://mishil-production.up.railway.app/api/v1',
    hapticPulse: () => {},
    showToast: () => {},
    fetch: async () => ({ ok: true }),
    navigator: { userAgent: 'iPhone' },
    localStorage: {
      getItem: (k) => (storage.has(k) ? storage.get(k) : null),
      setItem: (k, v) => storage.set(k, String(v)),
      removeItem: (k) => storage.delete(k),
    },
    document: {
      visibilityState: 'visible',
      addEventListener: () => {},
      getElementById: (id) => ({
        id,
        style: { display: 'none' },
        classList: {
          contains: (cls) => cls === 'active' && activeOverlays.has(id),
        },
      }),
      querySelector: (sel) => {
        if (sel === '.modal-overlay.active') {
          for (const id of activeOverlays) {
            if (id.startsWith('modal-') || id === 'vip-renewal-modal') {
              return { id };
            }
          }
        }
        return null;
      },
    },
    window: {
      MishilNative: {
        isNative: opts.isNative !== false,
        storeReviewBridge: opts.storeReviewBridge !== false,
      },
      ReactNativeWebView: opts.hasWebView === false ? undefined : {
        postMessage: (str) => postedMessages.push(JSON.parse(str)),
      },
      open: () => {},
    },
  };
  sandbox.window.localStorage = sandbox.localStorage;
  sandbox.window.document = sandbox.document;

  vm.runInNewContext(blockCode, sandbox, { filename: 'delightEngine.extracted.js' });

  return {
    sandbox,
    window: sandbox.window,
    storage,
    postedMessages,
    activeOverlays,
  };
}

describe('WebView 5-Trigger Delight Review Engine (public/app.html)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('verifies zero review-gating markup (#rating-step-question removed from app.html)', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    expect(html.includes('id="rating-step-question"')).toBe(false);
    expect(html.includes('handleSentimentAnswer(')).toBe(false);
    expect(html.includes('id="settings-whisper-feedback-card"')).toBe(true);
  });

  it('Trigger 2 (+5s Continuous Sound): resets 5s timer on rapid track switch and fires once at 5s', () => {
    const ctx = createDelightEngineSandbox({ currentTrackId: 'white_noise' });

    ctx.window.armSoundDelightReviewTimer('white_noise');
    jest.advanceTimersByTime(3000);
    expect(ctx.postedMessages).toHaveLength(0);

    // Ebeveyn 3. saniyede hızlıca başka sese geçti -> sayaç sıfırlanmalı
    ctx.sandbox.currentTrackId = 'womb_sound';
    ctx.window.armSoundDelightReviewTimer('womb_sound');

    jest.advanceTimersByTime(3000); // İlk parçadan 6 sn, yeni parçadan 3 sn geçti -> henüz ateşlenmemeli!
    expect(ctx.postedMessages).toHaveLength(0);

    jest.advanceTimersByTime(2000); // Yeni parçada tam 5. saniye -> ateşlenmeli!
    expect(ctx.postedMessages).toEqual([
      { type: 'REQUEST_NATIVE_REVIEW', reason: 'sound_playing_5s' },
    ]);
  });

  it('Trigger 1 (+2s Live Sleep) & Trigger 4 (+10s Mışıl Dadı): fires first delight moment only once', () => {
    const ctx = createDelightEngineSandbox({ isSleeping: true });

    ctx.window.scheduleMishilDelightReview('live_sleep_started', 2000, () => !!ctx.sandbox.isSleeping);
    jest.advanceTimersByTime(2000);
    expect(ctx.postedMessages).toEqual([
      { type: 'REQUEST_NATIVE_REVIEW', reason: 'live_sleep_started' },
    ]);

    // Native katman onay döndüğünde 45 gün kilitlenir; ardından gelen Mışıl Dadı (+10s) tekrar açmaz
    ctx.window.onNativeReviewResult({ triggered: true, reason: 'ok', timestamp: Date.now() });
    ctx.window.scheduleMishilDelightReview('dadi_reply_completed', 10000);
    jest.advanceTimersByTime(10000);
    expect(ctx.postedMessages).toHaveLength(1);
  });

  it('Trigger 5 (Cry Analysis Calm Queue): never prompts during cry modal; prompts +3s on next calm open', () => {
    const ctx1 = createDelightEngineSandbox({ activeOverlays: ['modal-cry'] });
    ctx1.window.queueCryCalmDelightReview();
    expect(ctx1.storage.get('mishil_pending_delight_review')).toBe('1');
    expect(ctx1.postedMessages).toHaveLength(0);

    // Sonraki sakin açılış (modal yok)
    const ctx2 = createDelightEngineSandbox({
      initialStorage: Object.fromEntries(ctx1.storage),
    });
    ctx2.window.recordDistinctVisitAndCheckRating(true);
    jest.advanceTimersByTime(2900);
    expect(ctx2.postedMessages).toHaveLength(0);

    jest.advanceTimersByTime(200);
    expect(ctx2.postedMessages).toEqual([
      { type: 'REQUEST_NATIVE_REVIEW', reason: 'cry_calm_followup' },
    ]);
  });

  it('Safety Shields: blocks review within 60s after Paywall closes and fails silently on Build 67 without burning quota', () => {
    // 1. Paywall 60s shield
    const ctxPaywall = createDelightEngineSandbox();
    ctxPaywall.window.handleModalClosedSideEffects('vip-renewal-modal');
    ctxPaywall.window.scheduleMishilDelightReview('routine_logged', 2000);
    jest.advanceTimersByTime(2000);
    expect(ctxPaywall.postedMessages).toHaveLength(0);

    // 2. Build 67 backward-compatibility (storeReviewBridge = false)
    const ctxBuild67 = createDelightEngineSandbox({ storeReviewBridge: false });
    ctxBuild67.window.scheduleMishilDelightReview('routine_logged', 2000);
    jest.advanceTimersByTime(2000);
    expect(ctxBuild67.postedMessages).toHaveLength(0);
    expect(ctxBuild67.storage.has('mishil_native_review_last_ts')).toBe(false);
  });
});
