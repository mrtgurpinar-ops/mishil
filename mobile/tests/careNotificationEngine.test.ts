// @ts-nocheck
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

function loadCareNotificationEngine() {
  const filePath = path.resolve(__dirname, '../features/notifications/careNotificationEngine.ts');
  const source = fs.readFileSync(filePath, 'utf8');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });
  const mod = { exports: {} };
  const customRequire = (id) => {
    if (id === 'expo-notifications') return {};
    if (id === 'react-native') return { Platform: { OS: 'ios' } };
    if (id === '@react-native-async-storage/async-storage') return { getItem: async () => null, setItem: async () => {} };
    return require(id);
  };
  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', transpiled.outputText);
  fn(mod.exports, customRequire, mod, filePath, path.dirname(filePath));
  return mod.exports;
}

const {
  buildCareNotificationPlan,
  DEFAULT_NOTIFICATION_SETTINGS,
  getVaccineMilestonesForCountry,
} = loadCareNotificationEngine();

describe('CareNotificationEngine Unit Tests', () => {
  const mockReferenceDate = new Date('2026-10-23T12:00:00.000Z');

  it('should generate routine sleep notifications within the 14-day window', () => {
    const baby = {
      babyName: 'Atlas',
      babyBdate: '2026-06-01',
    };

    const plan = buildCareNotificationPlan(baby, DEFAULT_NOTIFICATION_SETTINGS, mockReferenceDate, 14);

    expect(plan.length).toBeGreaterThan(0);
    expect(plan.length).toBeLessThanOrEqual(14); // iOS 64 limit protection
    expect(plan.every((item) => item.title.includes('Atlas'))).toBe(true);
  });

  it('should prioritize VACCINE notifications and prevent routine duplication on the same day', () => {
    // 2. ay aşısı = 60 gün. 3 gün önce bildirim = doğumdan 57 gün sonra.
    const birthDate = new Date(mockReferenceDate);
    birthDate.setDate(birthDate.getDate() - 57);
    const bdateStr = birthDate.toISOString().split('T')[0];

    const baby = {
      babyName: 'Defne',
      babyBdate: bdateStr,
    };

    const plan = buildCareNotificationPlan(baby, DEFAULT_NOTIFICATION_SETTINGS, mockReferenceDate, 14);

    const vaccineItems = plan.filter((item) => item.type === 'VACCINE');
    expect(vaccineItems.length).toBeGreaterThan(0);
    expect(vaccineItems[0].title).toContain('Aşı');

    // Aynı gün (YYYY-MM-DD) için tek bir bildirim olmalı (deduplication)
    const dates = plan.map((item) => item.date.toISOString().split('T')[0]);
    const uniqueDates = new Set(dates);
    expect(dates.length).toBe(uniqueDates.size);
  });

  it('should schedule LEAP week notification when baby is at milestone week', () => {
    // 4. Atak = 19. hafta (19 * 7 = 133 gün). Doğum tarihi 131 gün önce olursa 2 gün sonra atak başlar!
    const birthDate = new Date(mockReferenceDate);
    birthDate.setDate(birthDate.getDate() - 131);
    const bdateStr = birthDate.toISOString().split('T')[0];

    const baby = {
      babyName: 'Lina',
      babyBdate: bdateStr,
    };

    const plan = buildCareNotificationPlan(baby, DEFAULT_NOTIFICATION_SETTINGS, mockReferenceDate, 14);

    const leapItems = plan.filter((item) => item.type === 'LEAP');
    expect(leapItems.length).toBeGreaterThan(0);
    expect(leapItems[0].title).toContain('19. Hafta Büyüme Sıçraması');
  });

  it('should safely fallback to "Bebeğiniz" when baby name is empty or whitespace', () => {
    const baby = {
      babyName: '   ',
      babyBdate: '2026-05-10',
    };

    const plan = buildCareNotificationPlan(baby, DEFAULT_NOTIFICATION_SETTINGS, mockReferenceDate, 14);
    expect(plan.length).toBeGreaterThan(0);
    expect(plan[0].title).toContain('Bebeğiniz');
  });

  it('should gracefully handle future birth date (pregnancy mode) without crashing', () => {
    const futureDate = new Date(mockReferenceDate);
    futureDate.setDate(futureDate.getDate() + 30);

    const baby = {
      babyName: 'Umut',
      babyBdate: futureDate.toISOString().split('T')[0],
    };

    const plan = buildCareNotificationPlan(baby, DEFAULT_NOTIFICATION_SETTINGS, mockReferenceDate, 14);
    const vaccineOrLeap = plan.filter((item) => item.type === 'VACCINE' || item.type === 'LEAP');
    expect(vaccineOrLeap.length).toBe(0);
  });

  it('should return empty list when all notification settings are disabled', () => {
    const baby = {
      babyName: 'Eren',
      babyBdate: '2026-04-01',
    };

    const disabledSettings = {
      vaccineEnabled: false,
      routineSleepEnabled: false,
      leapWeeksEnabled: false,
      routineTime: '20:30',
    };

    const plan = buildCareNotificationPlan(baby, disabledSettings, mockReferenceDate, 14);
    expect(plan.length).toBe(0);
  });

  it('should generate English notifications and keep identical IDs when lang is en or en-US', () => {
    const birthDate = new Date(mockReferenceDate);
    birthDate.setDate(birthDate.getDate() - 57);
    const bdateStr = birthDate.toISOString().split('T')[0];

    const planTr = buildCareNotificationPlan(
      { babyName: 'Leo', babyBdate: bdateStr, lang: 'tr-TR' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );
    const planEn = buildCareNotificationPlan(
      { babyName: 'Leo', babyBdate: bdateStr, lang: 'en-US' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );

    expect(planEn.length).toBe(planTr.length);
    expect(planEn.map((i) => i.id)).toEqual(planTr.map((i) => i.id));
    const vaccineEn = planEn.find((i) => i.type === 'VACCINE');
    expect(vaccineEn?.title).toContain('Vaccine');
    const routineEn = planEn.find((i) => i.type === 'ROUTINE_SLEEP');
    expect(routineEn?.title).toContain('Is Leo sleeping peacefully?');
  });

  it('should fallback to "Your Baby" in English mode when babyName is empty or default Turkish placeholder', () => {
    const plan = buildCareNotificationPlan(
      { babyName: 'Bebeğim', babyBdate: '2026-05-10', lang: 'en' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );
    expect(plan.length).toBeGreaterThan(0);
    expect(plan[0].title).toContain('Your Baby');
  });

  it('should use country-specific vaccine milestones (UK 3rd month NHS vs DE 11th month STIKO vs TR)', () => {
    const ukMilestones = getVaccineMilestonesForCountry('GB');
    expect(ukMilestones.some((m) => m.month === 3)).toBe(true);
    expect(ukMilestones.some((m) => m.month === 1)).toBe(false);

    const deMilestones = getVaccineMilestonesForCountry('DE');
    expect(deMilestones.some((m) => m.month === 11)).toBe(true);

    const azMilestones = getVaccineMilestonesForCountry('AZ');
    expect(azMilestones.some((m) => m.month === 3)).toBe(true);

    // 3. ay (90 gün) aşısı için 3 gün önce bildirim = doğumdan 87 gün sonra (UK veya AZ protokolünde var, TR'de yok)
    const birthDate = new Date(mockReferenceDate);
    birthDate.setDate(birthDate.getDate() - 86);
    const bdateStr = birthDate.toISOString().split('T')[0];

    const planTr = buildCareNotificationPlan(
      { babyName: 'Mila', babyBdate: bdateStr, lang: 'tr', vaccineCountry: 'TR' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );
    const planGb = buildCareNotificationPlan(
      { babyName: 'Mila', babyBdate: bdateStr, lang: 'tr', vaccineCountry: 'GB' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );

    expect(planTr.some((i) => i.type === 'VACCINE' && i.id.includes('3m'))).toBe(false);
    const gbVac3m = planGb.find((i) => i.type === 'VACCINE' && i.id.includes('3m'));
    expect(gbVac3m).toBeDefined();
    // Yurt dışında yaşayan Türkçe kullanıcıda "aile sağlığı merkezi" yerine "çocuk doktorunuzdan veya kliniğinizden" yazmalı
    expect(gbVac3m?.body).toContain('çocuk doktorunuzdan veya kliniğinizden');
  });

  it('should rotate evening ROUTINE_SLEEP notifications with zero consecutive duplicates and adapt to baby age bracket', () => {
    // 1) Yenidoğan (45 günlük -> newborn_0_3m)
    const newbornPlan = buildCareNotificationPlan(
      { babyName: 'Mert', babyBdate: '2026-09-08', lang: 'tr' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );
    const routineNewborn = newbornPlan.filter((i) => i.type === 'ROUTINE_SLEEP');
    expect(routineNewborn.length).toBeGreaterThan(5);
    expect(routineNewborn[0].ageBracket).toBe('newborn_0_3m');

    // Ardışık hiçbir gün birebir aynı başlık ve gövde olmamalı
    for (let idx = 1; idx < routineNewborn.length; idx++) {
      expect(routineNewborn[idx].title).not.toBe(routineNewborn[idx - 1].title);
      expect(routineNewborn[idx].body).not.toBe(routineNewborn[idx - 1].body);
    }

    // 14 gün içinde en az 5 farklı bildirim başlığı kullanılmalı (bildirim yorgunluğu engeli)
    const uniqueTitles = new Set(routineNewborn.map((i) => i.title));
    expect(uniqueTitles.size).toBeGreaterThanOrEqual(5);

    // Yenidoğana özel "Anne Karnı Huzuru" (v03_newborn_4th_trimester_womb) varyantı yer almalı
    expect(routineNewborn.some((i) => i.title.includes('Anne Karnı Huzuru'))).toBe(true);

    // 2) 10 Aylık Bebek (toddler_9m_plus) -> Yenidoğan anne karnı varyantı yerine Kelt Arpı / Keçe Piyano gelmeli
    const olderPlan = buildCareNotificationPlan(
      { babyName: 'Zeynep', babyBdate: '2025-12-15', lang: 'tr' },
      DEFAULT_NOTIFICATION_SETTINGS,
      mockReferenceDate,
      14
    );
    const routineOlder = olderPlan.filter((i) => i.type === 'ROUTINE_SLEEP');
    expect(routineOlder[0].ageBracket).toBe('toddler_9m_plus');
    expect(routineOlder.some((i) => i.title.includes('Anne Karnı Huzuru'))).toBe(false);
    expect(routineOlder.some((i) => i.title.includes('Kelt Uyku Arpı') || i.title.includes('Keçe Piyano'))).toBe(true);
  });

  it('should suppress today evening notification when baby is already live sleeping (isLiveSleepingToday) and skip completed vaccine months', () => {
    const birthDate = new Date(mockReferenceDate);
    birthDate.setDate(birthDate.getDate() - 57); // 2. ay aşısına 3 gün var
    const bdateStr = birthDate.toISOString().split('T')[0];

    const planWithSuppression = buildCareNotificationPlan(
      {
        babyName: 'Kaan',
        babyBdate: bdateStr,
        lang: 'tr',
        isLiveSleepingToday: true,
        completedVaccineMonths: [2],
      },
      { ...DEFAULT_NOTIFICATION_SETTINGS, routineFrequency: 'smart_4d' },
      mockReferenceDate,
      14
    );

    // 1) Bugün (2026-10-23) bebek zaten canlı uykuda olduğu için bugünkü akşam bildirimi atlanmış olmalı
    expect(planWithSuppression.some((i) => i.id === 'routine-sleep-2026-10-23')).toBe(false);
    // 2) 2. ay aşısı tamamlandı olarak işaretlendiği için 2. ay aşı hatırlatması atlanmış olmalı
    expect(planWithSuppression.some((i) => i.type === 'VACCINE' && i.id.includes('2m'))).toBe(false);
    // 3) smart_4d modunda 14 günde maksimum 10 bildirim planlanmalı (her 3. gün dinlenme)
    expect(planWithSuppression.length).toBeLessThanOrEqual(10);
  });
});
