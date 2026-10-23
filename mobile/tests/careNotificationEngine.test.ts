// T.C. Sağlık Bakanlığı Çocukluk Dönemi Aşı Takvimi Kilometre Taşları
const VACCINE_MILESTONES = [
  { day: 30, month: 1, label: '1. Ay Aşıları (Hepatit B 2. doz)' },
  { day: 60, month: 2, label: '2. Ay Aşıları (Verem/BCG, 5\'li Karma 1. doz, KPA 1. doz)' },
  { day: 120, month: 4, label: '4. Ay Aşıları (5\'li Karma 2. doz, KPA 2. doz)' },
  { day: 180, month: 6, label: '6. Ay Aşıları (Hepatit B 3. doz, 5\'li Karma 3. doz, Çocuk Felci)' },
  { day: 270, month: 9, label: '9. Ay Aşıları (Kızamık)' },
  { day: 365, month: 12, label: '12. Ay Aşıları (KKK, Suçiçeği, KPA Pekiştirme)' },
  { day: 540, month: 18, label: '18. Ay Aşıları (5\'li Karma Pekiştirme, Çocuk Felci, Hepatit A 1. doz)' },
  { day: 720, month: 24, label: '24. Ay Aşıları (Hepatit A 2. doz)' },
];

const LEAP_WEEKS = [
  { week: 5, title: '1. Sıçrama (Değişen Duyular)' },
  { week: 8, title: '2. Sıçrama (Oluşumlar & Desenler)' },
  { week: 12, title: '3. Sıçrama (Yumuşak Geçişler)' },
  { week: 19, title: '4. Sıçrama (4. Ay Uyku Gerilemesi)' },
  { week: 26, title: '5. Sıçrama (İlişkiler Dünyası)' },
  { week: 37, title: '6. Sıçrama (Kategoriler)' },
  { week: 46, title: '7. Sıçrama (Dizilimler)' },
  { week: 55, title: '8. Sıçrama (Programlar)' },
  { week: 64, title: '9. Sıçrama (İlkeler)' },
  { week: 75, title: '10. Sıçrama (Sistemler)' },
];

// @ts-ignore
function buildCareNotificationPlan(baby, settings, referenceDate = new Date(), windowDays = 14) {
  const items = [];
  const babyName = (baby.babyName && baby.babyName.trim()) || 'Bebeğiniz';

  let birthDate = null;
  if (baby.babyBdate) {
    const parsed = new Date(baby.babyBdate);
    if (!isNaN(parsed.getTime()) && parsed.getTime() <= referenceDate.getTime()) {
      birthDate = parsed;
    }
  }

  const windowStart = new Date(referenceDate);
  const windowEnd = new Date(referenceDate);
  windowEnd.setDate(windowEnd.getDate() + windowDays);

  const dayPlanMap = new Map();

  // @ts-ignore
  const formatDateKey = (d) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  if (settings.vaccineEnabled && birthDate) {
    for (const v of VACCINE_MILESTONES) {
      const milestoneDate = new Date(birthDate.getTime() + v.day * 24 * 60 * 60 * 1000);

      const notify3DaysBefore = new Date(milestoneDate);
      notify3DaysBefore.setDate(notify3DaysBefore.getDate() - 3);
      notify3DaysBefore.setHours(10, 30, 0, 0);

      if (notify3DaysBefore >= windowStart && notify3DaysBefore <= windowEnd) {
        const key = formatDateKey(notify3DaysBefore);
        dayPlanMap.set(key, {
          id: `vaccine-3d-${v.month}m-${key}`,
          date: notify3DaysBefore,
          title: `💉 ${babyName} için Aşı Zamanı Yaklaşıyor`,
          body: `${v.month}. ay aşıları için randevunuzu kontrol etmeyi unutmayın.`,
          type: 'VACCINE',
          priority: 1,
        });
      }

      const notify1DayBefore = new Date(milestoneDate);
      notify1DayBefore.setDate(notify1DayBefore.getDate() - 1);
      notify1DayBefore.setHours(10, 30, 0, 0);

      if (notify1DayBefore >= windowStart && notify1DayBefore <= windowEnd) {
        const key = formatDateKey(notify1DayBefore);
        dayPlanMap.set(key, {
          id: `vaccine-1d-${v.month}m-${key}`,
          date: notify1DayBefore,
          title: `💉 Yarın ${babyName} için Aşı Günü`,
          body: `${v.label} zamanı geldi.`,
          type: 'VACCINE',
          priority: 1,
        });
      }
    }
  }

  if (settings.leapWeeksEnabled && birthDate) {
    for (const leap of LEAP_WEEKS) {
      const leapStartDate = new Date(birthDate.getTime() + leap.week * 7 * 24 * 60 * 60 * 1000);
      leapStartDate.setHours(10, 30, 0, 0);

      if (leapStartDate >= windowStart && leapStartDate <= windowEnd) {
        const key = formatDateKey(leapStartDate);
        if (!dayPlanMap.has(key)) {
          dayPlanMap.set(key, {
            id: `leap-${leap.week}w-${key}`,
            date: leapStartDate,
            title: `⚡ ${babyName} için ${leap.week}. Hafta Büyüme Sıçraması`,
            body: `${leap.title} dönemi başladı!`,
            type: 'LEAP',
            priority: 2,
          });
        }
      }
    }
  }

  if (settings.routineSleepEnabled) {
    const [hourStr, minuteStr] = (settings.routineTime || '20:30').split(':');
    const routineHour = parseInt(hourStr || '20', 10);
    const routineMinute = parseInt(minuteStr || '30', 10);

    for (let dayOffset = 0; dayOffset < windowDays; dayOffset++) {
      const targetDay = new Date(referenceDate);
      targetDay.setDate(targetDay.getDate() + dayOffset);
      targetDay.setHours(routineHour, routineMinute, 0, 0);

      if (targetDay <= referenceDate) continue;

      const key = formatDateKey(targetDay);
      if (!dayPlanMap.has(key)) {
        dayPlanMap.set(key, {
          id: `routine-sleep-${key}`,
          date: targetDay,
          title: `🌙 ${babyName} mışıl mışıl uyudu mu?`,
          body: `Uykuya dalmakta zorlanıyorsa, pışpışlama seslerini tek dokunuşla başlatabilirsiniz.`,
          type: 'ROUTINE_SLEEP',
          priority: 3,
        });
      }
    }
  }

  for (const item of dayPlanMap.values()) {
    items.push(item);
  }
  items.sort((a, b) => a.date.getTime() - b.date.getTime());

  return items.slice(0, windowDays);
}

const DEFAULT_NOTIFICATION_SETTINGS = {
  vaccineEnabled: true,
  routineSleepEnabled: true,
  leapWeeksEnabled: true,
  routineTime: '20:30',
};

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
});
