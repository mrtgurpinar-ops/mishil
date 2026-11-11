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
});
