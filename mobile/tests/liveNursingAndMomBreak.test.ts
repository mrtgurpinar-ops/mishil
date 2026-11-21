// @ts-nocheck
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP_HTML_PATH = path.resolve(__dirname, '../../public/app.html');

function extractFuncBlock(code, signature) {
  const start = code.indexOf(signature);
  if (start === -1) throw new Error(`Missing signature: ${signature}`);
  let depth = 0;
  let started = false;
  for (let i = start; i < code.length; i++) {
    const ch = code[i];
    if (ch === '{') {
      depth++;
      started = true;
    } else if (ch === '}') {
      depth--;
      if (started && depth === 0) {
        return code.slice(start, i + 1);
      }
    }
  }
  throw new Error(`Unclosed block for: ${signature}`);
}

describe('Mışıl Baby v4.53.0 — Live Nursing Timer, Inclusivity & Mom Break Suite', () => {
  const html = fs.readFileSync(APP_HTML_PATH, 'utf8');
  const scriptCode = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

  it('1. computeLiveNursingTotals calculates lock-screen wall-clock deltas accurately and enforces 180-min cap', () => {
    const snippet = [
      'const LIVE_NURSING_MAX_DURATION_MS = 180 * 60 * 1000;',
      extractFuncBlock(scriptCode, 'function computeLiveNursingTotals('),
    ].join('\n');

    const ctx = {};
    vm.runInNewContext(snippet, ctx);

    const t0 = 1763500000000;
    // Left ran 7 mins earlier, Right has been running for 11 mins while phone screen was locked
    const res = ctx.computeLiveNursingTotals(
      {
        sessionStartedAt: t0,
        activeSide: 'right',
        activeSideStartedAt: t0 + 7 * 60000,
        leftAccumMs: 7 * 60000,
        rightAccumMs: 0,
      },
      t0 + 18 * 60000
    );
    expect(res.leftMs).toBe(7 * 60000);
    expect(res.rightMs).toBe(11 * 60000);
    expect(res.totalMs).toBe(18 * 60000);
    expect(res.capped).toBe(false);

    // Negative clock skew never produces negative durations
    const skewRes = ctx.computeLiveNursingTotals(
      {
        sessionStartedAt: t0,
        activeSide: 'left',
        activeSideStartedAt: t0 + 5000,
        leftAccumMs: 120000,
        rightAccumMs: 0,
      },
      t0
    );
    expect(skewRes.leftMs).toBe(120000);
    expect(skewRes.capped).toBe(false);

    // Forgotten timer (>180 min) caps cleanly at 180 min
    const cappedRes = ctx.computeLiveNursingTotals(
      {
        sessionStartedAt: t0,
        activeSide: 'left',
        activeSideStartedAt: t0,
        leftAccumMs: 0,
        rightAccumMs: 30 * 60000,
      },
      t0 + 240 * 60000
    );
    expect(cappedRes.capped).toBe(true);
    expect(cappedRes.totalMs).toBe(180 * 60000);
    expect(cappedRes.leftMs + cappedRes.rightMs).toBe(180 * 60000);
  });

  it('2. resolveLocalizedRoutineCopy localizes structured breast side (left / right / both) across TR, EN, and DE', () => {
    const snippet = [
      'let currentLang = "tr";',
      'function getAppLang() { return currentLang; }',
      'function _planActiveLang() { return currentLang; }',
      extractFuncBlock(scriptCode, 'function resolveLocalizedRoutineCopy('),
    ].join('\n');

    const ctx = {
      setLang: (l) => { ctx._setL(l); },
    };
    vm.runInNewContext(
      snippet + '\nthis._setL = function(l) { currentLang = l; }; this.resolve = resolveLocalizedRoutineCopy;',
      ctx
    );

    const sampleBoth = {
      type: 'feeding',
      method: 'breast',
      side: 'both',
      leftMin: 12,
      rightMin: 8,
      durationMin: 20,
    };

    ctx._setL('tr');
    expect(ctx.resolve(sampleBoth).detail).toContain('Sol 12 dk + Sağ 8 dk');
    expect(ctx.resolve({ type: 'feeding', method: 'breast', side: 'right', durationMin: 15 }).detail).toContain('Sağ Göğüs');

    ctx._setL('en');
    expect(ctx.resolve(sampleBoth).detail).toContain('Left 12m + Right 8m');
    expect(ctx.resolve({ type: 'feeding', method: 'breast', side: 'left', durationMin: 10 }).detail).toContain('Left Breast');

    ctx._setL('de');
    expect(ctx.resolve(sampleBoth).detail).toContain('Links 12 Min. + Rechts 8 Min.');
    expect(ctx.resolve({ type: 'feeding', method: 'breast', side: 'right', durationMin: 14 }).detail).toContain('Rechte Brust');
  });

  it('3. getPreferredFeedMethodForModal respects formula/solid onboarding choice (inclusivity guard)', () => {
    const snippet = [
      'var activeRoutines = [];',
      'var onboardingFeedMethod = "formula";',
      extractFuncBlock(scriptCode, 'function getPreferredFeedMethodForModal('),
    ].join('\n');

    const store = {};
    const ctx = {
      localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
      },
    };
    vm.runInNewContext(snippet + '\nthis.getPref = getPreferredFeedMethodForModal;', ctx);

    // Formula onboarding -> bottle_formula (never forces breast stopwatch by default!)
    expect(ctx.getPref()).toBe('bottle_formula');

    // Explicit saved preference overrides
    store.mishil_preferred_feed_method = 'breast';
    expect(ctx.getPref()).toBe('breast');
  });

  it('4. v4.53.0 UI strings exist in both EN and DE translation maps and first-sleep review shield is present', () => {
    expect(html).toContain('"⏱️ Canlı Emzirme Sayacı": "⏱️ Live Nursing Stopwatch"');
    expect(html).toContain('"⏱️ Canlı Emzirme Sayacı": "⏱️ Live-Stilluhr"');
    expect(html).toContain('"🌙 Memede Uyudu": "🌙 Fell Asleep Nursing"');
    expect(html).toContain('"🌙 Memede Uyudu": "🌙 Eingeschlafen"');
    expect(html).toContain("mishil_sleep_delight_seen");
    // Ensure zero auto-scrollIntoView was added to syncMomBreakDrawerVisibility or toggleLiveSleep
    const momSyncBlock = extractFuncBlock(scriptCode, 'function syncMomBreakDrawerVisibility(');
    expect(momSyncBlock).not.toContain('scrollIntoView');
  });

  it('5. End-to-end session persist/restore, mid-session VIP expiry survival, and dream-feed non-duplication', () => {
    const snippet = [
      'const LIVE_NURSING_STORAGE_KEY = "mishil_live_nursing_state";',
      'const LAST_NURSING_SIDE_KEY = "mishil_last_nursing_side";',
      'const LIVE_NURSING_MAX_DURATION_MS = 180 * 60 * 1000;',
      'let isNursing = false; let liveNursingState = null; let liveNursingInterval = null;',
      'let isSleeping = false; let editingRoutineId = null; let onboardingFeedMethod = "breast";',
      'let activeRoutines = []; let vipActive = true; let toggleSleepCalls = 0;',
      'function hapticPulse() {} function hapticImpact() {} function showToast() {}',
      'function trEnDe(tr) { return tr; } function _planActiveLang() { return "tr"; }',
      'function formatTimeHHMM() { return "03:20"; }',
      'function sortActiveRoutines() {} function broadcastRealtimeEvent() {} function pushFamilySyncDebounced() {}',
      'function renderHomeTodayTimeline() {} function renderHomeScreenScore() {} function renderAnalyticsView() {}',
      'function syncMomBreakDrawerVisibility() {} function triggerMomDrawerRevealGlow() {} function scheduleMishilDelightReview() {}',
      'function requireActiveSubscription() { return vipActive; }',
      'function toggleLiveSleep() { toggleSleepCalls++; isSleeping = !isSleeping; }',
      extractFuncBlock(scriptCode, 'function formatMmSsFromMs('),
      extractFuncBlock(scriptCode, 'function computeLiveNursingTotals('),
      extractFuncBlock(scriptCode, 'function persistLiveNursingState('),
      extractFuncBlock(scriptCode, 'function ensureLiveNursingTicker('),
      extractFuncBlock(scriptCode, 'function resolveLocalizedRoutineCopy('),
      'function syncLiveNursingUI() {} function syncLiveNursingToNative() {}',
      extractFuncBlock(scriptCode, 'function toggleLiveNursingSide('),
      extractFuncBlock(scriptCode, 'function completeLiveNursingSession('),
      extractFuncBlock(scriptCode, 'function checkAndRestoreLiveNursing('),
    ].join('\n');

    const store = {};
    const ctx = {
      document: { getElementById: () => null, body: { classList: { contains: () => false } } },
      localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
      },
      setInterval: () => 1,
      clearInterval: () => {},
      Date,
      Math,
      Number,
      JSON,
    };
    vm.runInNewContext(
      snippet + '\nthis._api = { toggle: toggleLiveNursingSide, complete: completeLiveNursingSession, restore: checkAndRestoreLiveNursing, setSleep: (v) => { isSleeping = v; }, setVip: (v) => { vipActive = v; }, getRoutines: () => activeRoutines, getSleepCalls: () => toggleSleepCalls, resetRam: () => { isNursing = false; liveNursingState = null; } };',
      ctx
    );

    // Start nursing on Left while VIP active, persist, simulate reload + VIP expiry mid-session
    expect(ctx._api.toggle('left')).toBe(true);
    expect(store.mishil_live_nursing_state).toBeTruthy();
    const persisted = JSON.parse(store.mishil_live_nursing_state);
    persisted.leftAccumMs = 90000;
    store.mishil_live_nursing_state = JSON.stringify(persisted);
    ctx._api.resetRam();
    ctx._api.setVip(false); // Trial expired mid-session!
    ctx._api.restore();

    // Switch to Right and save while Dream Feeding (isSleeping === true): must NOT hit Paywall and must NOT double-start sleep!
    ctx._api.setSleep(true);
    expect(ctx._api.toggle('right')).toBe(true);
    const saved = ctx._api.complete(true);
    expect(saved).toBeTruthy();
    expect(saved.type).toBe('feeding');
    expect(saved.method).toBe('breast');
    expect(saved.leftMin).toBe(2);
    expect(saved.durationMin).toBeGreaterThanOrEqual(2);
    expect(ctx._api.getSleepCalls()).toBe(0); // Dream feed preserved active sleep without toggling!
    expect(store.mishil_last_nursing_side).toBe('right');
    expect(store.mishil_live_nursing_state).toBeUndefined();
  });

  it('6. v4.54.0 Zero Cognitive Load: isolated baby/mom chat histories, independent mom free quota, nursing bar above fold & PARTNER_WHISPER sync', () => {
    // Active nursing bar must appear BEFORE #home-organic-hero so it never falls below the fold
    expect(html.indexOf('id="home-live-nursing-bar"')).toBeLessThan(html.indexOf('id="home-organic-hero"'));
    // Removed clutter modules must NOT remain in DOM
    expect(html).not.toContain('id="mom-panel-lantern"');
    expect(html).not.toContain('id="mom-panel-escape"');
    expect(html).not.toContain('id="mom-puzzle-input"');
    expect(html).not.toContain('id="mom-morning-note-input"');
    expect(html).not.toContain('id="btn-modal-nursing-companion"');
    // WebSocket must listen for backend PARTNER_WHISPER event
    expect(scriptCode).toContain("msg.type === 'PARTNER_WHISPER'");
    // v4.55.0 Hard Paywall: Coach & Mom Corner strictly require active VIP subscription (zero free question bypass)
    expect(scriptCode).toContain("const isMomDadiPaywall = contextFeature === 'ai_nanny' && typeof activeDadiAudience !== 'undefined' && activeDadiAudience === 'mom';");
    // E2E & Adversarial QA Regression Guards: fetchWithTimeout, applyLanguage, 0s nursing guard, ackedWhisperIds & double-tap whisper lock
    expect(scriptCode).toContain('async function fetchWithTimeout(resource, options)');
    expect(scriptCode).toContain('window.applyLanguage = applyLanguage;');
    expect(scriptCode).toContain('if (totals.totalMs <= 0)');
    expect(scriptCode).toContain('recordAckedWhisperId(w.id)');
    expect(scriptCode).toContain('if (isDispatchingWhisper || (nowW - lastWhisperSentAtMs < 1200)) return;');

    // Verify Hard Paywall blocks unsubscribed Dadi access for both 'baby' and 'mom', and unlocks when VIP is active
    const quotaSnippet = [
      'let activeDadiAudience = "baby";',
      'let vipActive = false;',
      'function isSubscriptionCurrentlyActive() { return vipActive; }',
      'function isPaidOrVerifiedVip() { return vipActive; }',
      'function syncDeviceQuotasToNative() {}',
      extractFuncBlock(scriptCode, 'function hasUsedFreeDadiQuestion('),
      extractFuncBlock(scriptCode, 'function hasUsedFreeMomDadiQuestion('),
      extractFuncBlock(scriptCode, 'function canAskDadiQuestion('),
      extractFuncBlock(scriptCode, 'function markFreeDadiQuestionUsedIfNeeded('),
    ].join('\n');

    const store = {};
    const ctx = {
      localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
      },
    };
    vm.runInNewContext(
      quotaSnippet + '\nthis._q = { canAsk: canAskDadiQuestion, setVip: (v) => { vipActive = v; } };',
      ctx
    );

    expect(ctx._q.canAsk('baby')).toBe(false);
    expect(ctx._q.canAsk('mom')).toBe(false);
    ctx._q.setVip(true);
    expect(ctx._q.canAsk('baby')).toBe(true);
    expect(ctx._q.canAsk('mom')).toBe(true);
  });

  it('7. v4.54.1 Live Nursing Lock Screen / Live Activity bridge: Build 70 immediate compatibility, Build 71 V2 pause freeze & Dream-Feed sleep restoration', () => {
    const sentMessages = [];
    const store = {
      mishil_baby_name: 'Atlas',
      mishil_lockscreen_show_name: '1',
    };

    const bridgeSnippet = [
      'var LIVE_NURSING_STORAGE_KEY = "mishil_live_nursing_state";',
      'var LAST_NURSING_SIDE_KEY = "mishil_last_nursing_side";',
      'var LIVE_NURSING_MAX_DURATION_MS = 180 * 60 * 1000;',
      'var isNursing = false;',
      'var liveNursingState = null;',
      'var liveNursingInterval = null;',
      'var isSleeping = false;',
      'var sleepStartTime = null;',
      'var nursingNativeSyncTimer = null;',
      'var lastNativeActivityDispatched = null;',
      'function getAppLang() { return "tr"; }',
      'function trEnDe(t, _e, _d) { return t; }',
      'function nativeAudioSend(obj) { __pushMsg(obj); }',
      extractFuncBlock(scriptCode, 'function formatMmSsFromMs('),
      extractFuncBlock(scriptCode, 'function computeLiveNursingTotals('),
      extractFuncBlock(scriptCode, 'function hasNursingLockScreenV2('),
      extractFuncBlock(scriptCode, 'function syncLiveSleepToNative('),
      extractFuncBlock(scriptCode, 'function dispatchLiveNursingToNativeNow('),
      extractFuncBlock(scriptCode, 'function syncLiveNursingToNative('),
      extractFuncBlock(scriptCode, 'function reconcileActiveLockscreenActivity('),
    ].join('\n');

    const ctx = {
      window: {
        ReactNativeWebView: { postMessage: () => {} },
        MishilNative: { liveSleepBridge: true, nursingLockScreenV2: false },
      },
      localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
      },
      Date,
      Math,
      Number,
      String,
      Boolean,
      setTimeout,
      clearTimeout,
      __pushMsg: (m) => sentMessages.push(m),
    };
    vm.runInNewContext(
      bridgeSnippet +
        '\nthis._api = { syncNursing: syncLiveNursingToNative, syncSleep: syncLiveSleepToNative, reconcile: reconcileActiveLockscreenActivity, setState: (s) => { isNursing = s.isNursing; liveNursingState = s.liveNursingState; isSleeping = s.isSleeping; sleepStartTime = s.sleepStartTime; } };',
      ctx
    );

    const refNow = Date.now();
    // 1) Build 70 (nursingLockScreenV2 = false): active left breast sends LIVE_SLEEP_START with 🤱 prefix, showBabyNameOnLockScreen=false, and baby name in subtitle
    ctx._api.setState({
      isNursing: true,
      liveNursingState: {
        sessionStartedAt: refNow - 180000,
        activeSide: 'left',
        activeSideStartedAt: refNow - 60000,
        leftAccumMs: 120000,
        rightAccumMs: 60000,
        lastTouchedSide: 'left',
      },
      isSleeping: false,
      sleepStartTime: null,
    });
    ctx._api.syncNursing('START', { immediate: true });
    expect(sentMessages.length).toBe(1);
    expect(sentMessages[0]).toEqual(
      expect.objectContaining({
        type: 'LIVE_SLEEP_START',
        sleepLabel: '🤱 Emzirme · Sol Göğüs',
        showBabyNameOnLockScreen: false,
        mode: 'nursing',
        isPaused: false,
      })
    );
    expect(sentMessages[0].subtitle).toContain('Atlas · Sol 03:00 · Sağ 01:00');
    expect(Math.abs((refNow - 240000) - sentMessages[0].startEpochMs)).toBeLessThan(1500);

    // 2) Build 70 pause: stops hardware clock so Lock Screen never ticks falsely
    sentMessages.length = 0;
    ctx._api.setState({
      isNursing: true,
      liveNursingState: {
        sessionStartedAt: refNow - 240000,
        activeSide: null,
        activeSideStartedAt: 0,
        leftAccumMs: 180000,
        rightAccumMs: 60000,
        lastTouchedSide: 'left',
      },
      isSleeping: false,
      sleepStartTime: null,
    });
    ctx._api.syncNursing('UPDATE', { immediate: true });
    expect(sentMessages[0]).toEqual({ type: 'LIVE_SLEEP_STOP' });

    // 3) Build 71+ (nursingLockScreenV2 = true) pause: keeps frozen paused state on Lock Screen!
    sentMessages.length = 0;
    ctx.window.MishilNative.nursingLockScreenV2 = true;
    ctx._api.syncNursing('UPDATE', { immediate: true });
    expect(sentMessages[0]).toEqual(
      expect.objectContaining({
        type: 'LIVE_SLEEP_UPDATE',
        sleepLabel: 'Emzirme · Duraklatıldı',
        mode: 'nursing',
        isPaused: true,
        pausedElapsedSec: 240,
      })
    );

    // 4) Dream-Feed (isSleeping = true while nursing finishes): immediately restores original sleepStartTime!
    sentMessages.length = 0;
    const origSleepDate = new Date(refNow - 45 * 60000);
    ctx._api.setState({
      isNursing: false,
      liveNursingState: null,
      isSleeping: true,
      sleepStartTime: origSleepDate,
    });
    ctx._api.syncNursing('STOP', { immediate: true });
    expect(sentMessages[0]).toEqual(
      expect.objectContaining({
        type: 'LIVE_SLEEP_START',
        startEpochMs: origSleepDate.getTime(),
        mode: 'sleep',
        isPaused: false,
      })
    );

    // 5) Build 70 foreground reconcile WITHOUT activityMode: stale sleep activity on Lock Screen is replaced by active nursing!
    sentMessages.length = 0;
    ctx.window.MishilNative.nursingLockScreenV2 = false;
    ctx._api.setState({
      isNursing: true,
      liveNursingState: {
        sessionStartedAt: refNow - 120000,
        activeSide: 'right',
        activeSideStartedAt: refNow - 60000,
        leftAccumMs: 60000,
        rightAccumMs: 0,
        lastTouchedSide: 'right',
      },
      isSleeping: true,
      sleepStartTime: origSleepDate,
    });
    ctx._api.reconcile({ sleepActive: true, sleepStartEpochMs: origSleepDate.getTime() }); // Build 70 omits activityMode!
    expect(sentMessages.length).toBe(1);
    expect(sentMessages[0]).toEqual(
      expect.objectContaining({
        type: 'LIVE_SLEEP_START',
        sleepLabel: '🤱 Emzirme · Sağ Göğüs',
        mode: 'nursing',
      })
    );
  });

  test('8. v4.54.1: mapServerRoutineToClientItem preserves camelCase server timestamps, self-heals 07:25 poisoned yesterday logs without touching valid overnight/edited logs, and calibrates morning wake', () => {
    const appHtml = fs.readFileSync(APP_HTML_PATH, 'utf8');
    const startIdx = appHtml.indexOf('function parseRoutineHHMMStrict(');
    const endIdx = appHtml.indexOf('function hydrateClientStateFromFamilySnapshot(');
    expect(startIdx).toBeGreaterThan(0);
    expect(endIdx).toBeGreaterThan(startIdx);

    const spotStart = appHtml.indexOf('function calculateMışılSpot(');
    const spotEnd = appHtml.indexOf('// 10 Scientific BabySteps', spotStart);
    expect(spotStart).toBeGreaterThan(0);
    expect(spotEnd).toBeGreaterThan(spotStart);

    const nowMorning = new Date(2026, 10, 20, 7, 26, 0); // 20 Nov 2026 07:26 local
    const yestCreatedMs = new Date(2026, 10, 19, 22, 46, 0).getTime(); // 19 Nov 2026 22:46 local
    const yestTrueStartMs = new Date(2026, 10, 19, 21, 30, 0).getTime();
    const yestTrueEndMs = new Date(2026, 10, 19, 22, 45, 0).getTime();
    const poisoned725Ms = new Date(2026, 10, 20, 7, 25, 12).getTime();

    const vmCtx = {
      window: {},
      Date,
      Math,
      Number,
      String,
      Array,
      Object,
      isNaN,
      parseInt,
      localStorage: {
        getItem: () => null,
      },
      activeRoutines: [],
      getAppLang: () => 'tr',
      trEnDe: (tr) => tr,
      getPrematureWeeksStored: () => 0,
      isSameLocalCalendarDay: (a, b) =>
        a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(),
      formatPlanDayTimeLabel: (dt, now) => {
        const hhmm = `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
        if (dt.getDate() === now.getDate()) return hhmm;
        return `Dün ${hhmm}`;
      },
      WONDER_WEEKS_LEAPS: [{ num: 1, startWeek: 4, endWeek: 5, stormWeek: 5, title: 'Duyular' }],
      getActiveLeapNumber: () => 1,
      getLeapTitle: (l) => l.title,
    };

    vm.runInNewContext(
      appHtml.slice(startIdx, endIdx) + '\n' + appHtml.slice(spotStart, spotEnd),
      vmCtx
    );

    // A) CamelCase server routine (family.py output without timestamp_ms/end_ts) preserves exact yesterday timestamps!
    const mapped = vmCtx.mapServerRoutineToClientItem({
      id: `slp_${yestCreatedMs}_xy12`,
      type: 'sleep',
      title: 'Gece Uykusu',
      start: '21:30',
      end: '22:45',
      time: '22:45',
      timestamp: yestTrueEndMs,
      startTs: yestTrueStartMs,
      endTs: yestTrueEndMs,
      durationMins: 75,
      sleepKind: 'night',
      actorName: 'Anne',
    });
    expect(mapped.endTs).toBe(yestTrueEndMs);
    expect(mapped.startTs).toBe(yestTrueStartMs);
    expect(mapped.timestamp).toBe(yestTrueEndMs);
    expect(mapped.actorName).toBe('Anne');
    expect(mapped.sleepKind).toBe('night');

    // B) Self-heal already-poisoned 07:25 yesterday sleep & feeding logs, WITHOUT touching valid overnight (21:30 -> 06:45) or user-edited logs!
    const validOvernightStart = new Date(2026, 10, 19, 21, 30, 0).getTime();
    const validOvernightEnd = new Date(2026, 10, 20, 6, 45, 0).getTime();
    const validEditedEnd = new Date(2026, 10, 20, 6, 55, 0).getTime();

    const mixedList = [
      {
        id: `slp_${yestCreatedMs}_pois`,
        type: 'sleep',
        start: '21:30',
        end: '22:45',
        time: '22:45',
        durationMins: 75,
        startTs: poisoned725Ms - 75 * 60000,
        endTs: poisoned725Ms,
        timestamp: poisoned725Ms,
      },
      {
        id: `rt_${new Date(2026, 10, 19, 19, 10, 0).getTime()}`,
        type: 'feeding',
        time: '19:10',
        timestamp: poisoned725Ms,
      },
      {
        id: `slp_${validOvernightEnd}_ok`,
        type: 'sleep',
        start: '21:30',
        end: '06:45',
        time: '06:45',
        durationMins: 555,
        startTs: validOvernightStart,
        endTs: validOvernightEnd,
        timestamp: validOvernightEnd,
      },
      {
        id: `slp_${yestCreatedMs}_edit`,
        type: 'sleep',
        start: '05:45',
        end: '06:55',
        time: '06:55',
        durationMins: 70,
        startTs: validEditedEnd - 70 * 60000,
        endTs: validEditedEnd,
        timestamp: validEditedEnd,
        editedAtMs: nowMorning.getTime(),
      },
      {
        id: 'onb_slp_init',
        type: 'sleep',
        sleepKind: 'onb_nap',
        end: '06:45',
        time: '06:45',
        endTs: poisoned725Ms,
        timestamp: poisoned725Ms,
      },
    ];

    const healRes = vmCtx.repairCorruptedRoutineTimestamps(mixedList, nowMorning);
    expect(healRes.repairedCount).toBe(2);

    // Yesterday's sleep snapped back to 19 Nov 21:30 -> 22:45 (strictly before 20 Nov 00:00 todayStart!)
    const todayStartMs = new Date(2026, 10, 20, 0, 0, 0).getTime();
    expect(mixedList[0].endTs).toBe(yestTrueEndMs);
    expect(mixedList[0].startTs).toBe(yestTrueStartMs);
    expect(mixedList[0].endTs).toBeLessThan(todayStartMs);
    expect(mixedList[1].timestamp).toBe(new Date(2026, 10, 19, 19, 10, 0).getTime());

    // Valid overnight & user-edited logs remained 100% untouched!
    expect(mixedList[2].endTs).toBe(validOvernightEnd);
    expect(mixedList[2].startTs).toBe(validOvernightStart);
    expect(mixedList[2].repairedAtMs).toBeUndefined();
    expect(mixedList[3].endTs).toBe(validEditedEnd);
    expect(mixedList[3].repairedAtMs).toBeUndefined();

    // C) Morning MışılSpot calibration when only yesterday's night log exists (>= 6h gap across midnight)
    const RealDate = Date;
    vmCtx.Date = class extends RealDate {
      constructor(...args) {
        if (args.length === 0) {
          super(nowMorning.getTime());
        } else {
          super(...args);
        }
      }
      static now() {
        return nowMorning.getTime();
      }
    };
    vmCtx.activeRoutines = [mixedList[0]]; // Only yesterday 22:45 sleep
    const morningCalc = vmCtx.calculateMışılSpot('2026-08-15');
    expect(morningCalc.needsWakeCalibration).toBe(true);
    expect(morningCalc.isOverdue).toBe(false);
    expect(morningCalc.heroDisplayTime).toBe('☀️ Uyanış?');
    expect(morningCalc.statusNote).toContain('Dün 22:45');
  });
});
