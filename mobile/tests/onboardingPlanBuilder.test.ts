// @ts-nocheck
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function createOnboardingEngineSandbox(initialStorage = {}) {
  const htmlPath = path.resolve(__dirname, '../../public/app.html');
  const html = fs.readFileSync(htmlPath, 'utf8').replace(/\r\n/g, '\n');

  const startMarker = '// === ONBOARDING COMBOBOX & PERSONAL PLAN BUILDER ENGINE (v4.49.0) ===';
  const endMarker = '// === END ONBOARDING COMBOBOX & PERSONAL PLAN BUILDER ENGINE (v4.49.0) ===';
  const startIdx = html.indexOf(startMarker);
  const endIdx = html.indexOf(endMarker, startIdx);
  if (startIdx === -1 || endIdx === -1) {
    throw new Error('Could not locate Onboarding Plan Builder Engine block in public/app.html');
  }
  const blockCode = html.slice(startIdx, endIdx + endMarker.length);

  const storage = new Map(Object.entries(initialStorage));
  const sandbox = {
    Date,
    Math,
    JSON,
    Number,
    String,
    Boolean,
    Array,
    Object,
    parseInt,
    parseFloat,
    isNaN,
    localStorage: {
      getItem: (k) => (storage.has(k) ? storage.get(k) : null),
      setItem: (k, v) => storage.set(k, String(v)),
      removeItem: (k) => storage.delete(k),
    },
  };

  vm.runInNewContext(blockCode, sandbox, { filename: 'onboardingPlanBuilder.extracted.js' });
  return { sandbox, storage };
}

const SAMPLE_LEAPS = [
  { num: 1, startWeek: 4, endWeek: 5, stormWeek: 5, title: 'Değişen Duyular Dünyası', titleEn: 'World of Changing Sensations' },
  { num: 2, startWeek: 7, endWeek: 9, stormWeek: 8, title: 'Desenler ve Kalıplar Dünyası', titleEn: 'World of Patterns' },
  { num: 3, startWeek: 11, endWeek: 12, stormWeek: 12, title: 'Yumuşak Geçişler Dünyası', titleEn: 'World of Smooth Transitions' },
  { num: 4, startWeek: 15, endWeek: 19, stormWeek: 19, title: 'Olaylar Dünyası', titleEn: 'World of Events' },
];

const SAMPLE_TR_VACCINES = [
  { id: 'v_hepb_1', month: 0, name: 'Hepatit B (1. Doz)', nameEn: 'Hepatitis B (Dose 1)' },
  { id: 'v_hepb_2', month: 1, name: 'Hepatit B (2. Doz)', nameEn: 'Hepatitis B (Dose 2)' },
  { id: 'v_bcg', month: 2, name: 'BCG (Verem)', nameEn: 'BCG (Tuberculosis)' },
  { id: 'v_karma_1', month: 2, name: '5\'li Karma (1. Doz)', nameEn: 'DTaP-IPV-Hib (Dose 1)' },
  { id: 'v_karma_2', month: 4, name: '5\'li Karma (2. Doz)', nameEn: 'DTaP-IPV-Hib (Dose 2)' },
  { id: 'v_hepb_3', month: 6, name: 'Hepatit B (3. Doz)', nameEn: 'Hepatitis B (Dose 3)' },
];

describe('Onboarding Combobox & Personal Plan Builder Engine (v4.49.0)', () => {
  it('verifies zero text/keyboard inputs inside #screen-onboarding and presence of #modal-post-paywall-profile', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    const onbStart = html.indexOf('<div id="screen-onboarding"');
    const mainStart = html.indexOf('<div class="screen-container no-scrollbar" id="main-app-screen">');
    expect(onbStart).toBeGreaterThan(-1);
    expect(mainStart).toBeGreaterThan(onbStart);

    const onboardingMarkup = html.slice(onbStart, mainStart);
    expect(onboardingMarkup.includes('type="text"')).toBe(false);
    expect(onboardingMarkup.includes('<textarea')).toBe(false);
    expect(onboardingMarkup.includes('id="quiz-step-6"')).toBe(true);
    expect(onboardingMarkup.includes('id="quiz-step-7"')).toBe(true);
    expect(onboardingMarkup.includes('id="quiz-step-8"')).toBe(true);
    expect(onboardingMarkup.includes('id="report-personal-insights-card"')).toBe(true);
    expect(html.includes('id="modal-post-paywall-profile"')).toBe(true);
  });

  it('clampBirthDateParts handles Gregorian leap years, 30-day months, and future date clamping', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 14, 0, 0); // 11 Nov 2026

    // Leap year 2024 allows Feb 29
    const leap2024 = sandbox.clampBirthDateParts(2024, 2, 29, now);
    expect(leap2024.iso).toBe('2024-02-29');

    // Non-leap year 2025 clamps Feb 29 -> Feb 28
    const nonLeap2025 = sandbox.clampBirthDateParts(2025, 2, 29, now);
    expect(nonLeap2025.iso).toBe('2025-02-28');

    // April 31 -> April 30
    const apr30 = sandbox.clampBirthDateParts(2026, 4, 31, now);
    expect(apr30.iso).toBe('2026-04-30');

    // Future month/day in current year clamps to today (2026-11-11)
    const futureMonth = sandbox.clampBirthDateParts(2026, 12, 25, now);
    expect(futureMonth.iso).toBe('2026-11-11');
    const futureDay = sandbox.clampBirthDateParts(2026, 11, 28, now);
    expect(futureDay.iso).toBe('2026-11-11');
  });

  it('clampedAddMonths prevents month-end overflow (Jan 31 + 1 month -> Feb 28, never Mar 3)', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const jan31NonLeap = sandbox.clampedAddMonths('2026-01-31', 1);
    expect(jan31NonLeap.getFullYear()).toBe(2026);
    expect(jan31NonLeap.getMonth()).toBe(1); // Feb (0-indexed)
    expect(jan31NonLeap.getDate()).toBe(28);

    const jan31Leap = sandbox.clampedAddMonths('2024-01-31', 1);
    expect(jan31Leap.getFullYear()).toBe(2024);
    expect(jan31Leap.getMonth()).toBe(1);
    expect(jan31Leap.getDate()).toBe(29);
  });

  it('autoAdjustDayModeForHour and resolveRoutineEventTimestamp handle 00:30 night watch vs daytime clamp', () => {
    const { sandbox } = createOnboardingEngineSandbox();

    // Night shift at 00:30 selecting 23:00 auto-switches dayMode to yesterday
    const nightNow = new Date(2026, 10, 11, 0, 30, 0);
    expect(sandbox.autoAdjustDayModeForHour(23, 'today', nightNow)).toBe('yesterday');
    const nightTs = sandbox.resolveRoutineEventTimestamp('yesterday', 23, 15, nightNow);
    const nightDt = new Date(nightTs);
    expect(nightDt.getDate()).toBe(10);
    expect(nightDt.getHours()).toBe(23);
    expect(nightDt.getMinutes()).toBe(15);

    // Daytime at 14:20 selecting 15:00 on 'today' clamps to 14:20 today (never yesterday)
    const dayNow = new Date(2026, 10, 11, 14, 20, 0);
    expect(sandbox.autoAdjustDayModeForHour(15, 'today', dayNow)).toBe('today');
    const clampedTs = sandbox.resolveRoutineEventTimestamp('today', 15, 0, dayNow);
    const clampedDt = new Date(clampedTs);
    expect(clampedDt.getDate()).toBe(11);
    expect(clampedDt.getHours()).toBe(14);
    expect(clampedDt.getMinutes()).toBe(20);
  });

  it('getCumulativeLeapsForBaby applies premature correction for BabySteps™ and handles newborns (<4 weeks)', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 12, 0, 0);

    // Born 10 weeks ago (70 days): chronological = Week 10 (Leaps 1 & 2 completed, Leap 3 upcoming)
    const tenWeeksAgo = '2026-09-02';
    const fullTerm = sandbox.getCumulativeLeapsForBaby(tenWeeksAgo, 0, SAMPLE_LEAPS, now);
    expect(fullTerm.chronoWeek).toBe(10);
    expect(fullTerm.effectiveWeek).toBe(10);
    expect(fullTerm.items.map((x) => `${x.leap.num}:${x.status}`)).toEqual([
      '1:completed',
      '2:completed',
      '3:upcoming',
    ]);

    // Same birth date, born 6 weeks premature -> effectiveWeek = 4 (Leap 1 active, Leap 2 not yet reached!)
    const premBaby = sandbox.getCumulativeLeapsForBaby(tenWeeksAgo, 6, SAMPLE_LEAPS, now);
    expect(premBaby.chronoWeek).toBe(10);
    expect(premBaby.effectiveWeek).toBe(4);
    expect(premBaby.items.map((x) => `${x.leap.num}:${x.status}`)).toEqual(['1:active']);

    // Newborn 10 days old -> includeNewbornSensory: true + Leap 1 upcoming
    const newborn = sandbox.getCumulativeLeapsForBaby('2026-11-01', 0, SAMPLE_LEAPS, now);
    expect(newborn.effectiveWeek).toBe(1);
    expect(newborn.includeNewbornSensory).toBe(true);
    expect(newborn.items[0].leap.num).toBe(1);
    expect(newborn.items[0].status).toBe('upcoming');
    expect(newborn.items[0].defaultChecked).toBe(false);
  });

  it('getCumulativeDueVaccinesForBirthDate uses chronological age (birth..today) and supports UK/schedule fallback', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 12, 0, 0); // 11 Nov 2026

    // Baby born 3 months ago (11 Aug 2026) -> Month 0, Month 1, Month 2 vaccines are due; Month 4 is nextUpcoming
    const res3m = sandbox.getCumulativeDueVaccinesForBirthDate('2026-08-11', SAMPLE_TR_VACCINES, now);
    expect(res3m.isFallbackUpcoming).toBe(false);
    expect(res3m.dueVaccines.map((x) => x.vaccine.id)).toEqual([
      'v_hepb_1',
      'v_hepb_2',
      'v_bcg',
      'v_karma_1',
    ]);
    expect(res3m.nextUpcomingVaccine.id).toBe('v_karma_2');

    // Schedule starting at Month 2 (e.g. UK NHS) for a 2-week-old newborn -> fallback shows Month 2 first vaccines
    const ukStyleSchedule = [
      { id: 'uk_6in1_1', month: 2, name: '6-in-1 (Dose 1)' },
      { id: 'uk_rotavirus_1', month: 2, name: 'Rotavirus (Dose 1)' },
      { id: 'uk_6in1_2', month: 3, name: '6-in-1 (Dose 2)' },
    ];
    const ukNewborn = sandbox.getCumulativeDueVaccinesForBirthDate('2026-11-01', ukStyleSchedule, now);
    expect(ukNewborn.isFallbackUpcoming).toBe(true);
    expect(ukNewborn.dueVaccines.map((x) => x.vaccine.id)).toEqual(['uk_6in1_1', 'uk_rotavirus_1']);
  });

  it('upsertOnboardingRoutineEntry updates idempotently on Back/Next and deletes cleanly on Skip without touching user logs', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const userLog = { id: 'usr_999', type: 'feeding', timestamp: 1700000000000, title: 'Anne Sütü' };

    // Insert initial onboarding feeding entry
    let list = sandbox.upsertOnboardingRoutineEntry(
      [userLog],
      { type: 'feeding', timestamp: 1700003600000, title: 'Mama' },
      'onb_feed_init'
    );
    expect(list).toHaveLength(2);
    expect(list[0].id).toBe('onb_feed_init');
    expect(list[0].title).toBe('Mama');

    // User goes back and edits feeding method -> replaces onb_feed_init without duplicating
    list = sandbox.upsertOnboardingRoutineEntry(
      list,
      { type: 'feeding', timestamp: 1700005000000, title: 'Ek Gıda' },
      'onb_feed_init'
    );
    expect(list).toHaveLength(2);
    expect(list.filter((r) => r.id === 'onb_feed_init')).toHaveLength(1);
    expect(list[0].title).toBe('Ek Gıda');

    // User goes back and clicks "Skip" -> removes onb_feed_init while preserving userLog
    list = sandbox.upsertOnboardingRoutineEntry(list, null, 'onb_feed_init');
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe('usr_999');
  });

  it('computePersonalReportInsights reflects real sleep, hunger overlap, observed leaps, and missing due vaccines', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 14, 0, 0); // 14:00

    // 3-month-old baby (wake window 75m): woke at 13:15 -> next MışılSpot 14:30.
    // Last fed at 11:30 -> at 14:30 it will be 180 mins (>=150m), triggering Hunger × Sleep warning!
    // Missing 1 due vaccine (v_karma_1 unticked).
    const wakeTs = new Date(2026, 10, 11, 13, 15, 0).getTime();
    const feedTs = new Date(2026, 10, 11, 11, 30, 0).getTime();
    const diaperTs = new Date(2026, 10, 11, 13, 0, 0).getTime();

    const report = sandbox.computePersonalReportInsights({
      lang: 'tr',
      nowDate: now,
      bdate: '2026-08-11',
      prematureWeeks: 0,
      lastWakeTs: wakeTs,
      liveSleepStartIso: '',
      routines: [
        { id: 'onb_slp_init', type: 'sleep', endTs: wakeTs, timestamp: wakeTs, time: '13:15' },
        { id: 'onb_feed_init', type: 'feeding', timestamp: feedTs, time: '11:30', detail: 'Anne Sütü' },
        { id: 'onb_diaper_init', type: 'diaper', timestamp: diaperTs, time: '13:00', detail: 'Islak Bez' },
      ],
      checkedLeaps: { '1': true, '2': true },
      completedVaccines: {
        v_hepb_1: { done: true },
        v_hepb_2: { done: true },
        v_bcg: { done: true },
        // v_karma_1 intentionally left unticked!
      },
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
      manualLeap: null,
    });

    expect(report.wakeWindowMin).toBe(75);
    expect(report.sweetSpotTimeStr).toBe('14:30');
    expect(report.isLiveSleepingNow).toBe(false);
    expect(report.isOverdueNow).toBe(false);
    expect(report.sleepInsight).toContain('14:30');
    expect(report.feedingInsight).toContain('Açlık × Uyku Analizi');
    expect(report.feedingInsight).toContain('Son bez (13:00) işlendi');
    expect(report.leapsInsight).toContain('2/10');
    expect(report.vaccineInsight).toContain('3/4 Tamam');
    expect(report.vaccineInsight).toContain('1 aşı vakti geldi');
  });

  it('prevents DOM XSS via inline JS handlers or unescaped custom vaccine/routine payloads', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    // Checklist handlers must read data-* attributes rather than interpolating string literals into onclick
    expect(html.includes("toggleOnboardingVaccineItem('${")).toBe(false);
    expect(html.includes("toggleOnboardingLeapItem('${")).toBe(false);
    expect(html.includes("data-vac-id=\"${escapeHtml(v.id)}\"")).toBe(true);

    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 14, 0, 0);
    const report = sandbox.computePersonalReportInsights({
      lang: 'tr',
      nowDate: now,
      bdate: '2026-08-11',
      routines: [
        {
          id: 'onb_feed_init',
          type: 'feeding',
          timestamp: now.getTime() - 30 * 60000,
          time: '13:30"><img src=x onerror=alert(1)>',
          detail: '<script>alert(2)</script>',
        },
      ],
      completedVaccines: {},
      schedule: [
        { id: "v_xss');alert(1)//", month: 0, name: '<svg onload=alert(3)>' },
      ],
      leapsList: SAMPLE_LEAPS,
    });

    expect(report.feedingInsight).not.toContain('<img');
    expect(report.feedingInsight).not.toContain('<script>');
    expect(report.feedingInsight).toContain('&lt;script&gt;');
    expect(report.vaccineInsight).not.toContain('<svg');
    expect(report.vaccineInsight).toContain('&lt;svg onload=alert(3)&gt;');
  });

  it('diffCalendarDays and getCumulativeLeapsForBaby use UTC calendar days without DST 23h/25h boundary drift', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    // Simulate a Date with a spring-forward +1h timezone offset change between March 1 and March 29 at 00:15 local time
    // Even at 00:15 on March 29, calendar days since March 1 MUST be exact 28 (Week 4 -> Leap 1 active)
    const march29EarlyMorning = new Date(2026, 2, 29, 0, 15, 0);
    expect(sandbox.diffCalendarDays('2026-03-01', march29EarlyMorning)).toBe(28);

    const leapAt4w = sandbox.getCumulativeLeapsForBaby('2026-03-01', 0, SAMPLE_LEAPS, march29EarlyMorning);
    expect(leapAt4w.chronoDays).toBe(28);
    expect(leapAt4w.effectiveWeek).toBe(4);
    expect(leapAt4w.items[0].leap.num).toBe(1);
    expect(leapAt4w.items[0].status).toBe('active');
  });

  it('promotes mishil_onb_live_sleep_draft across all onboarding completion flows so live sleep timer activates', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    const clearMatches = html.match(/localStorage\.removeItem\('mishil_onb_live_sleep_draft'\)/g) || [];
    // Cleared in clearOnboardingLiveSleepDraftIfAny, onPurchaseSuccess, activateTrialAndStart, skipOnboardingToApp, submitReviewerPin, restoreVipRenewalPurchases, and checkAndRestoreLiveSleep
    expect(clearMatches.length).toBeGreaterThanOrEqual(7);
  });

  it('splits Step 8 (Personal Report) and Step 9 (Focused Paywall) with Apple 3.1.2c annual price primacy and immediate skip', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    const step8Idx = html.indexOf('id="quiz-step-8"');
    const step9Idx = html.indexOf('id="quiz-step-9"');
    const mainIdx = html.indexOf('id="main-app-screen"');
    expect(step8Idx).toBeGreaterThan(-1);
    expect(step9Idx).toBeGreaterThan(step8Idx);
    expect(mainIdx).toBeGreaterThan(step9Idx);

    const step8Html = html.slice(step8Idx, step9Idx);
    const step9Html = html.slice(step9Idx, mainIdx);

    // Step 8 focuses strictly on personal report + locked evening roadmap CTA, with zero plan cards
    expect(step8Html.includes('id="report-next-sweetspot-time"')).toBe(true);
    expect(step8Html.includes('id="report-locked-roadmap-card"')).toBe(true);
    expect(step8Html.includes('id="btn-report-unlock-plan"')).toBe(true);
    expect(step8Html.includes('id="onboarding-plan-monthly"')).toBe(false);

    // Step 9 contains focused paywall, immediate skip (opacity: 1), legal links, and Reviewer PIN trigger
    expect(step9Html.includes('id="onboarding-plan-monthly"')).toBe(true);
    expect(step9Html.includes('id="onboarding-plan-yearly"')).toBe(true);
    expect(step9Html.includes('id="btn-onboarding-pro"')).toBe(true);
    expect(step9Html.includes('id="onboarding-skip-wrap" style="text-align: center; margin-top: 8px; opacity: 1;"')).toBe(true);
    expect(step9Html.includes('id="paywall-version-trigger"')).toBe(true);

    // Apple Guideline 3.1.2c: total annual billed amount (.price-yearly-text) must precede monthly equivalent (.price-yearly-monthly-eq-text)
    const yearlyCardStart = step9Html.indexOf('id="onboarding-plan-yearly"');
    const yearlySlice = step9Html.slice(yearlyCardStart, yearlyCardStart + 1400);
    expect(yearlySlice.indexOf('price-yearly-text')).toBeGreaterThan(-1);
    expect(yearlySlice.indexOf('price-yearly-monthly-eq-text')).toBeGreaterThan(yearlySlice.indexOf('price-yearly-text'));
  });

  it('computePersonalReportInsights distinguishes estimated vs logged wake and generates locked evening roadmap & tr/en/de chips', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 11, 14, 0, 0); // 14:00

    // Case 1: User skipped Step 2 (no wake log, not sleeping) -> honest isEstimatedWake: true
    const estReportEn = sandbox.computePersonalReportInsights({
      lang: 'en',
      nowDate: now,
      bdate: '2026-07-11', // 4 months -> wakeWindow 95m, bedtime 19:30 -> 19:••
      routines: [],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });
    expect(estReportEn.isEstimatedWake).toBe(true);
    expect(estReportEn.hasLoggedWake).toBe(false);
    expect(estReportEn.wakeSourceLine).toContain('initial estimate');
    expect(estReportEn.nextNapLockedMask).toMatch(/^\d{2}:••$/);
    expect(estReportEn.idealBedtimeMask).toBe('19:••');
    expect(estReportEn.chips.feedChip).toContain('Feeding');
    expect(estReportEn.chips.vaccineChip).toContain('Due');

    // Case 2: Logged wake in German -> hasLoggedWake: true, isEstimatedWake: false
    const wakeTs = new Date(2026, 10, 11, 13, 0, 0).getTime();
    const loggedDe = sandbox.computePersonalReportInsights({
      lang: 'de',
      nowDate: now,
      bdate: '2026-07-11',
      lastWakeTs: wakeTs,
      routines: [{ id: 'onb_slp_init', type: 'sleep', endTs: wakeTs, timestamp: wakeTs, time: '13:00' }],
      checkedLeaps: { '1': true },
      completedVaccines: {
        v_hepb_1: { done: true },
        v_hepb_2: { done: true },
        v_bcg: { done: true },
        v_karma_1: { done: true },
        v_karma_2: { done: true },
      },
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });
    expect(loggedDe.hasLoggedWake).toBe(true);
    expect(loggedDe.isEstimatedWake).toBe(false);
    expect(loggedDe.sweetSpotTimeStr).toBe('14:45');
    expect(loggedDe.nextNapLockedMask).toBe('17:••');
    expect(loggedDe.chips.vaccineChip).toBe('💉 Impfpass aktuell ✓');
  });

  it('enforces honest 1-shot Freemium value gate without 24h cardless Soft VIP trial cannibalization', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    expect(html.includes('var SOFT_VIP_DURATION_MS = 0;')).toBe(true);
    expect(html.includes('return !isSubscriptionCurrentlyActive() && hasUsedFirstFreeSpotAha();')).toBe(true);
    expect(html.includes("localStorage.setItem('mishil_first_spot_aha_used', '1');")).toBe(true);
    expect(html.includes("localStorage.setItem('mishil_free_sound_used', '1');")).toBe(true);
    expect(html.includes("localStorage.setItem('mishil_free_cry_used', '1');")).toBe(true);
    expect(html.includes('mishil_onb_live_sleep_promoted')).toBe(true);
    expect(html.includes('skipQuotaConsume: true')).toBe(true);
    expect(html.includes('freeSoundPreviewTrackId')).toBe(true);
    expect(html.includes('chk-medical-disclaimer')).toBe(false);
    expect(html.includes('toggleDisclaimerConsent')).toBe(false);

    // Multi-surface paywall compliance on #vip-renewal-modal as well
    const modalIdx = html.indexOf('id="vip-renewal-modal"');
    expect(modalIdx).toBeGreaterThan(0);
    const modalChunk = html.slice(modalIdx, modalIdx + 12000);
    expect(modalChunk.indexOf('price-yearly-text')).toBeGreaterThan(0);
    expect(modalChunk.indexOf('price-yearly-text')).toBeLessThan(modalChunk.indexOf('price-yearly-monthly-eq-text'));
    expect(modalChunk.includes('id="vip-renewal-timeline-day7-text"')).toBe(true);
    expect(modalChunk.includes('/terms')).toBe(true);
    expect(modalChunk.includes('/privacy')).toBe(true);
    expect(modalChunk.includes('handleReviewerTap()')).toBe(true);

    // Cross-language Back navigation (Step 9 -> Step 8) & Native Build 68 post-paywall naming sync
    expect(html.includes('generateSleepReport({ preservePlan: true, silentHaptic: true })')).toBe(true);
    expect(html.includes('window.__mishilWasExitingOnboarding')).toBe(true);
    expect(html.includes('openVipRenewalModal(lastVipRenewalFeature, { silentRefresh: true })')).toBe(true);
  });

  it('v4.50.2: aligns overdue MışılSpot displayTimeStr to current clock, labels Yesterday/Today, advances locked 2nd nap, and honors sleepStepSkipped', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    // Reproduce user test screenshot: 5-month-old baby (wakeWindow 105m), woke Yesterday at 13:25, evaluated Today at 07:36
    const now = new Date(2026, 10, 12, 7, 36, 0); // 12 Nov 2026 07:36
    const wakeYesterdayTs = new Date(2026, 10, 11, 13, 25, 0).getTime(); // 11 Nov 2026 13:25

    const overdueTr = sandbox.computePersonalReportInsights({
      lang: 'tr',
      nowDate: now,
      bdate: '2026-06-20',
      lastWakeTs: wakeYesterdayTs,
      routines: [
        { id: 'onb_slp_init', type: 'sleep', endTs: wakeYesterdayTs, timestamp: wakeYesterdayTs, time: '13:25' },
      ],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });

    expect(overdueTr.wakeWindowMin).toBe(105);
    expect(overdueTr.isOverdueNow).toBe(true);
    // Raw target stays HH:MM ('15:10'), while displayTimeStr aligns to current clock ('07:36')
    expect(overdueTr.sweetSpotTimeStr).toBe('15:10');
    expect(overdueTr.displayTimeStr).toBe('07:36');
    expect(overdueTr.wakeSourceLine).toContain('Dün 13:25');
    expect(overdueTr.wakeSourceLine).toContain('Hedef (Dün 15:10) geçti');
    expect(overdueTr.sleepInsight).toContain('16 sa 26 dk');
    // 2nd nap advances from max(now=07:36, nextSpot=yesterday 15:10) + (45 + 105)m = 10:06 -> '10:••'
    expect(overdueTr.nextNapLockedMask).toBe('10:••');

    // Same scenario when user explicitly clicked "Skip for now" on Step 2 -> ignores stale sleep logs
    const skippedTr = sandbox.computePersonalReportInsights({
      lang: 'tr',
      nowDate: now,
      bdate: '2026-06-20',
      sleepStepSkipped: true,
      lastWakeTs: wakeYesterdayTs,
      routines: [
        { id: 'old_slp_99', type: 'sleep', endTs: wakeYesterdayTs, timestamp: wakeYesterdayTs, time: '13:25' },
      ],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });
    expect(skippedTr.isOverdueNow).toBe(false);
    expect(skippedTr.isEstimatedWake).toBe(true);
    expect(skippedTr.displayTimeStr).toBe('09:21');
  });

  it('v4.50.2: storage.ts merges device quotas monotonically in SecureStore and preserves them across clearPersonalAppData', async () => {
    const ts = require('typescript');
    const storagePath = path.resolve(__dirname, '../lib/storage.ts');
    const source = fs.readFileSync(storagePath, 'utf8');
    const transpiled = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
    });

    const secureMap = new Map();
    const asyncMap = new Map([
      ['@mishil_baby_profile', '{"babyName":"Mina"}'],
      ['@mishil_onboarding_completed', 'true'],
      ['mishil_active_baby_id', 'b1'],
    ]);

    const mod = { exports: {} };
    const customRequire = (id) => {
      if (id === 'react-native') return { Platform: { OS: 'ios' } };
      if (id === 'expo-secure-store') {
        return {
          getItemAsync: async (k) => {
            await new Promise((r) => setTimeout(r, 5));
            return secureMap.has(k) ? secureMap.get(k) : null;
          },
          setItemAsync: async (k, v) => {
            await new Promise((r) => setTimeout(r, 5));
            secureMap.set(k, String(v));
          },
          deleteItemAsync: async (k) => { secureMap.delete(k); },
        };
      }
      if (id === '@react-native-async-storage/async-storage') {
        return {
          getItem: async (k) => (asyncMap.has(k) ? asyncMap.get(k) : null),
          setItem: async (k, v) => { asyncMap.set(k, String(v)); },
          removeItem: async (k) => { asyncMap.delete(k); },
          multiRemove: async (keys) => { keys.forEach((k) => asyncMap.delete(k)); },
        };
      }
      return require(id);
    };
    const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', transpiled.outputText);
    fn(mod.exports, customRequire, mod, storagePath, path.dirname(storagePath));
    const { storage, DEVICE_QUOTAS_KEY } = mod.exports;

    await storage.setToken('jwt_secret_123');
    await storage.mergeDeviceQuotas({ onboardedOnce: true, firstSpotUsed: true, freeSoundElapsedMs: 24500 });
    // Attempting to downgrade booleans or elapsed ms must be ignored monotonically
    const merged = await storage.mergeDeviceQuotas({ onboardedOnce: false, firstSpotUsed: false, freeSoundElapsedMs: 5000, freeDadiUsed: true });
    expect(merged.onboardedOnce).toBe(true);
    expect(merged.firstSpotUsed).toBe(true);
    expect(merged.freeDadiUsed).toBe(true);
    expect(merged.freeSoundElapsedMs).toBe(24500);

    // Account deletion wipes personal profile/token in SecureStore & AsyncStorage while preserving anonymous device quotas
    await storage.clearPersonalAppData();
    expect(await storage.getToken()).toBeNull();
    expect(asyncMap.has('@mishil_baby_profile')).toBe(false);
    expect(asyncMap.has('@mishil_onboarding_completed')).toBe(false);
    expect(secureMap.has(DEVICE_QUOTAS_KEY)).toBe(true);

    const postDeleteQuotas = await storage.getDeviceQuotas();
    expect(postDeleteQuotas.onboardedOnce).toBe(true);
    expect(postDeleteQuotas.firstSpotUsed).toBe(true);
    expect(postDeleteQuotas.freeDadiUsed).toBe(true);
    expect(postDeleteQuotas.freeSoundElapsedMs).toBe(24500);

    // Concurrent calls must serialize cleanly via deviceQuotaMutex without overwriting each other
    await Promise.all([
      storage.mergeDeviceQuotas({ freeCryUsed: true }),
      storage.mergeDeviceQuotas({ freeSoundElapsedMs: 58900 }),
      storage.mergeDeviceQuotas({ freeSoundElapsedMs: 12000 }),
    ]);
    const afterConcurrent = await storage.getDeviceQuotas();
    expect(afterConcurrent.freeCryUsed).toBe(true);
    expect(afterConcurrent.freeDadiUsed).toBe(true);
    expect(afterConcurrent.freeSoundElapsedMs).toBe(58900);
  });

  it('v4.50.2: enforces cumulative 60s sound timer, Spotlight zero-drift, full-width drawer, and 3-layer repeat-onboarding shield', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');

    // Full-width stacked drawer + Spotlight zero-drift hooks
    expect(html.includes('body.spotlight-tour-open .tab-view.active')).toBe(true);
    expect(html.includes('function updateSpotlightGeometry(')).toBe(true);
    expect(html.includes('target.scrollIntoView({ behavior: \'smooth\'')).toBe(false);

    // Cumulative 60s sound preview + unified native AUDIO_TIMER cap (sub-second exact without 1000ms inflation)
    expect(html.includes('var FREE_SOUND_PREVIEW_TOTAL_MS = 60000;')).toBe(true);
    expect(html.includes('mishil_free_sound_elapsed_ms')).toBe(true);
    expect(html.includes('Math.min(Math.max(1, remainingMs), freeCapMs)')).toBe(true);

    // 3-layer Freemium anti-repeat + Keychain bridge hooks
    expect(html.includes("openVipRenewalModal('restart_quiz')")).toBe(true);
    expect(html.includes('if (!isSubscriptionCurrentlyActive() && isRepeatDeviceOnboarding())')).toBe(true);
    expect(html.includes('if (prev === 8 && !isSubscriptionCurrentlyActive() && isRepeatDeviceOnboarding())')).toBe(true);
    expect(html.includes("type: 'CLEAR_PERSONAL_DATA'")).toBe(true);
    expect(html.includes("type: 'SYNC_DEVICE_QUOTAS'")).toBe(true);
  });

  it('v4.51.1: handles >24h "Yesterday" (Dün 06:45 at 07:34 = 1489m) without discarding wake log and surfaces Şimdi/Now/Jetzt hero', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const now = new Date(2026, 10, 13, 7, 34, 0); // 13 Nov 2026 07:34
    const wakeYesterdayMorningTs = new Date(2026, 10, 12, 6, 45, 0).getTime(); // 12 Nov 2026 06:45 (1489 mins ago)

    const trRes = sandbox.computePersonalReportInsights({
      lang: 'tr',
      nowDate: now,
      bdate: '2026-06-20',
      lastWakeTs: wakeYesterdayMorningTs,
      routines: [
        { id: 'onb_slp_init', type: 'sleep', endTs: wakeYesterdayMorningTs, timestamp: wakeYesterdayMorningTs, time: '06:45' },
      ],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });

    expect(trRes.isEstimatedWake).toBe(false);
    expect(trRes.hasLoggedWake).toBe(true);
    expect(trRes.isOverdueNow).toBe(true);
    expect(trRes.heroDisplayStr).toBe('Şimdi');
    expect(trRes.wakeSourceLine).toContain('Dün 06:45');
    expect(trRes.wakeSourceLine).toContain('24 sa 49 dk önce');
    expect(trRes.wakeSourceLine).toContain('Hedef (Dün 08:30) geçti');

    const enRes = sandbox.computePersonalReportInsights({
      lang: 'en',
      nowDate: now,
      bdate: '2026-06-20',
      lastWakeTs: wakeYesterdayMorningTs,
      routines: [
        { id: 'onb_slp_init', type: 'sleep', endTs: wakeYesterdayMorningTs, timestamp: wakeYesterdayMorningTs, time: '06:45' },
      ],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });
    expect(enRes.heroDisplayStr).toBe('Now');
    expect(enRes.wakeSourceLine).toContain('Yesterday 06:45');
    expect(enRes.wakeSourceLine).toContain('24h 49m ago');

    const deRes = sandbox.computePersonalReportInsights({
      lang: 'de',
      nowDate: now,
      bdate: '2026-06-20',
      lastWakeTs: wakeYesterdayMorningTs,
      routines: [
        { id: 'onb_slp_init', type: 'sleep', endTs: wakeYesterdayMorningTs, timestamp: wakeYesterdayMorningTs, time: '06:45' },
      ],
      checkedLeaps: {},
      completedVaccines: {},
      schedule: SAMPLE_TR_VACCINES,
      leapsList: SAMPLE_LEAPS,
    });
    expect(deRes.heroDisplayStr).toBe('Jetzt');
    expect(deRes.wakeSourceLine).toContain('Gestern 06:45 Uhr');
  });

  it('v4.51.1: preserves onboarding routines (onb_slp_init/feed/diaper) in skipOnboardingToApp and supports multi-day date & active-day average', () => {
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8');

    // 1. skipOnboardingToApp no longer deletes onb_slp_init / onb_feed_init / onb_diaper_init or mishil_onboarding_last_wake_ts
    const skipIdx = html.indexOf('function skipOnboardingToApp(');
    expect(skipIdx).toBeGreaterThan(0);
    const skipSlice = html.slice(skipIdx, skipIdx + 1600);
    expect(skipSlice.includes("localStorage.setItem('mishil_first_spot_aha_used', '1')")).toBe(true);
    expect(skipSlice.includes("r.id !== 'onb_slp_init'")).toBe(false);
    expect(skipSlice.includes("removeItem('mishil_onboarding_last_wake_ts')")).toBe(false);

    // 2. activeRoutines hoisted safely with var (no late let activeRoutines TDZ)
    expect(html.includes('var activeRoutines = [];')).toBe(true);
    expect(html.includes('let activeRoutines = JSON.parse')).toBe(false);

    // 3. Routine modal date picker + Analytics day-grouping & activeDaysCount average
    expect(html.includes('id="routine-modal-date"')).toBe(true);
    expect(html.includes('function resolveSleepTimestamps(startStr, endStr, referenceTs, referenceStartTs, explicitDateStr, nowRef)')).toBe(true);
    expect(html.includes('function formatRoutineGroupDayHeader(')).toBe(true);
    expect(html.includes('const activeDaysCount = buckets.filter(b => b.mins > 0).length;')).toBe(true);
    expect(html.includes('totalMins / (activeDaysCount * 60)')).toBe(true);
  });

  it('v4.51.1: resolveSleepTimestamps & resolveModalEventDate clamp future times on explicit "Bugün" instead of rolling back to yesterday, while preserving "Dün" & overnight ranges', () => {
    const { sandbox } = createOnboardingEngineSandbox();
    const htmlPath = path.resolve(__dirname, '../../public/app.html');
    const html = fs.readFileSync(htmlPath, 'utf8').replace(/\r\n/g, '\n');

    const isoFnStart = html.indexOf('function getLocalDateIsoString(dtObj)');
    const isoFnEnd = html.indexOf('function formatShortMonthDay(');
    expect(isoFnStart).toBeGreaterThan(0);
    expect(isoFnEnd).toBeGreaterThan(isoFnStart);

    const sliceStart = html.indexOf('function formatTimeHHMM(d)');
    const sliceEnd = html.indexOf('function shiftModalSleepTime(');
    expect(sliceStart).toBeGreaterThan(0);
    expect(sliceEnd).toBeGreaterThan(sliceStart);

    sandbox.window = sandbox;
    sandbox.document = { getElementById: () => null };
    sandbox.hapticSelection = () => {};
    sandbox.activeRoutines = [];
    vm.runInNewContext(
      html.slice(isoFnStart, isoFnEnd) + '\n' + html.slice(sliceStart, sliceEnd),
      sandbox,
      { filename: 'routineDateHelpers.extracted.js' }
    );

    const now = new Date(2026, 10, 13, 14, 20, 35); // 13 Nov 2026 14:20:35

    // 1. Explicit "Bugün" (2026-11-13) with future end time (13:00 -> 15:00):
    // Must stay on 2026-11-13 (clamped to 14:20, 80 mins), NEVER rolled back to 2026-11-12!
    const clampedNap = sandbox.resolveSleepTimestamps('13:00', '15:00', null, null, '2026-11-13', now);
    expect(sandbox.getLocalDateIsoString(clampedNap.endDate)).toBe('2026-11-13');
    expect(sandbox.formatTimeHHMM(clampedNap.startDate)).toBe('13:00');
    expect(sandbox.formatTimeHHMM(clampedNap.endDate)).toBe('14:20');
    expect(clampedNap.durMins).toBe(80);

    // 2. Explicit "Bugün" with both start & end in the future (15:00 -> 16:00):
    // Clamps endDate to 14:20 today and steps startDate back by 60m -> 13:20 today
    const bothFuture = sandbox.resolveSleepTimestamps('15:00', '16:00', null, null, '2026-11-13', now);
    expect(sandbox.getLocalDateIsoString(bothFuture.endDate)).toBe('2026-11-13');
    expect(sandbox.formatTimeHHMM(bothFuture.startDate)).toBe('13:20');
    expect(sandbox.formatTimeHHMM(bothFuture.endDate)).toBe('14:20');
    expect(bothFuture.durMins).toBe(60);

    // 3. Explicit "Dün" (2026-11-12) overnight sleep (22:30 -> 06:45):
    // Woke up on 2026-11-12 06:45, started on 2026-11-11 22:30 (495 mins)
    const yesterdayOvernight = sandbox.resolveSleepTimestamps('22:30', '06:45', null, null, '2026-11-12', now);
    expect(sandbox.getLocalDateIsoString(yesterdayOvernight.endDate)).toBe('2026-11-12');
    expect(sandbox.getLocalDateIsoString(yesterdayOvernight.startDate)).toBe('2026-11-11');
    expect(yesterdayOvernight.durMins).toBe(495);

    // 4. Feed/Diaper/Custom resolveModalEventDate parity on explicit "Bugün" vs "Dün"
    const clampedFeed = sandbox.resolveModalEventDate('2026-11-13', '16:30', null, now);
    expect(sandbox.getLocalDateIsoString(clampedFeed)).toBe('2026-11-13');
    expect(sandbox.formatTimeHHMM(clampedFeed)).toBe('14:20');

    const yesterdayFeed = sandbox.resolveModalEventDate('2026-11-12', '18:45', null, now);
    expect(sandbox.getLocalDateIsoString(yesterdayFeed)).toBe('2026-11-12');
    expect(sandbox.formatTimeHHMM(yesterdayFeed)).toBe('18:45');
  });
});
