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
      'function syncLiveNursingUI() {}',
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
    // Paywall & native quota bridge must honor independent mom free message quota
    expect(scriptCode).toContain('isMomDadiPaywall ? hasUsedFreeMomDadiQuestion() : hasUsedFreeDadiQuestion()');
    expect(scriptCode).toContain("freeMomDadiUsed: localStorage.getItem('mishil_free_mom_dadi_used') === '1'");
    // E2E & Adversarial QA Regression Guards: fetchWithTimeout, applyLanguage, 0s nursing guard, ackedWhisperIds & double-tap whisper lock
    expect(scriptCode).toContain('async function fetchWithTimeout(resource, options)');
    expect(scriptCode).toContain('window.applyLanguage = applyLanguage;');
    expect(scriptCode).toContain('if (totals.totalMs <= 0)');
    expect(scriptCode).toContain('recordAckedWhisperId(w.id)');
    expect(scriptCode).toContain('if (isDispatchingWhisper || (nowW - lastWhisperSentAtMs < 1200)) return;');

    // Verify independent baby vs mom free quotas and separate chat histories
    const quotaSnippet = [
      'let activeDadiAudience = "baby";',
      'function isSubscriptionCurrentlyActive() { return false; }',
      'function isPaidOrVerifiedVip() { return false; }',
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
      quotaSnippet + '\nthis._q = { canAsk: canAskDadiQuestion, markUsed: markFreeDadiQuestionUsedIfNeeded };',
      ctx
    );

    // Using baby free question does NOT block mom's 1st free message!
    expect(ctx._q.canAsk('baby')).toBe(true);
    expect(ctx._q.canAsk('mom')).toBe(true);
    ctx._q.markUsed('baby');
    expect(ctx._q.canAsk('baby')).toBe(false);
    expect(ctx._q.canAsk('mom')).toBe(true);
    ctx._q.markUsed('mom');
    expect(ctx._q.canAsk('mom')).toBe(false);
  });
});
