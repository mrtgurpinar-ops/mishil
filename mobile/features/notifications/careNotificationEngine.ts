import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type CareLang = 'tr' | 'en';

export function normalizeCareLang(raw?: string | null): CareLang {
  if (!raw || typeof raw !== 'string') return 'tr';
  const clean = raw.trim().toLowerCase();
  if (!clean) return 'tr';
  if (clean.startsWith('tr')) return 'tr';
  return 'en';
}

export interface NotificationSettings {
  vaccineEnabled: boolean;
  routineSleepEnabled: boolean;
  leapWeeksEnabled: boolean;
  routineTime: string; // e.g. "20:30"
  lang?: CareLang;
}

export interface BabyProfileData {
  babyName?: string;
  babyBdate?: string; // YYYY-MM-DD
  lang?: CareLang | string;
}

export interface CareNotificationPlanItem {
  id: string;
  date: Date;
  title: string;
  body: string;
  type: 'VACCINE' | 'LEAP' | 'ROUTINE_SLEEP';
  priority: number; // 1: VACCINE, 2: LEAP, 3: ROUTINE_SLEEP
}

export const DEFAULT_NOTIFICATION_SETTINGS: NotificationSettings = {
  vaccineEnabled: true,
  routineSleepEnabled: true,
  leapWeeksEnabled: true,
  routineTime: '20:30',
  lang: 'tr',
};

export const STORAGE_KEY_NOTIFICATION_SETTINGS = '@mishil_notification_settings';

// T.C. Sağlık Bakanlığı & WHO/CDC Çocukluk Dönemi Aşı Takvimi Kilometre Taşları (Doğum gününe göre gün cinsinden)
export const VACCINE_MILESTONES = [
  { day: 30, month: 1, label: '1. Ay Aşıları (Hepatit B 2. doz)', labelEn: 'Month 1 Vaccines (Hepatitis B Dose 2)' },
  { day: 60, month: 2, label: '2. Ay Aşıları (Verem/BCG, 5\'li Karma 1. doz, KPA 1. doz)', labelEn: 'Month 2 Vaccines (DTaP-IPV-Hib Dose 1, PCV13 Dose 1, BCG / Rotavirus per local schedule)' },
  { day: 120, month: 4, label: '4. Ay Aşıları (5\'li Karma 2. doz, KPA 2. doz)', labelEn: 'Month 4 Vaccines (DTaP-IPV-Hib Dose 2, PCV13 Dose 2)' },
  { day: 180, month: 6, label: '6. Ay Aşıları (Hepatit B 3. doz, 5\'li Karma 3. doz, Çocuk Felci)', labelEn: 'Month 6 Vaccines (Hepatitis B Dose 3, DTaP-IPV-Hib Dose 3)' },
  { day: 270, month: 9, label: '9. Ay Aşıları (Kızamık)', labelEn: 'Month 9 Vaccines (Measles / Checkup)' },
  { day: 365, month: 12, label: '12. Ay Aşıları (KKK, Suçiçeği, KPA Pekiştirme)', labelEn: 'Month 12 Vaccines (MMR, Varicella, PCV13 Booster)' },
  { day: 540, month: 18, label: '18. Ay Aşıları (5\'li Karma Pekiştirme, Çocuk Felci, Hepatit A 1. doz)', labelEn: 'Month 18 Vaccines (DTaP-IPV-Hib Booster, Hepatitis A Dose 1)' },
  { day: 720, month: 24, label: '24. Ay Aşıları (Hepatit A 2. doz)', labelEn: 'Month 24 Vaccines (Hepatitis A Dose 2)' },
];

// Wonder Weeks (Büyüme Sıçraması / Atak Haftaları - Doğum gününden sonraki haftalar)
export const LEAP_WEEKS = [
  { week: 5, title: '1. Sıçrama (Değişen Duyular)', titleEn: 'Leap 1 (Changing Sensations)' },
  { week: 8, title: '2. Sıçrama (Oluşumlar & Desenler)', titleEn: 'Leap 2 (Patterns)' },
  { week: 12, title: '3. Sıçrama (Yumuşak Geçişler)', titleEn: 'Leap 3 (Smooth Transitions)' },
  { week: 19, title: '4. Sıçrama (4. Ay Uyku Gerilemesi)', titleEn: 'Leap 4 (Events & 4-Month Sleep Regression)' },
  { week: 26, title: '5. Sıçrama (İlişkiler Dünyası)', titleEn: 'Leap 5 (Relationships)' },
  { week: 37, title: '6. Sıçrama (Kategoriler)', titleEn: 'Leap 6 (Categories)' },
  { week: 46, title: '7. Sıçrama (Dizilimler)', titleEn: 'Leap 7 (Sequences)' },
  { week: 55, title: '8. Sıçrama (Programlar)', titleEn: 'Leap 8 (Programs)' },
  { week: 64, title: '9. Sıçrama (İlkeler)', titleEn: 'Leap 9 (Principles)' },
  { week: 75, title: '10. Sıçrama (Sistemler)', titleEn: 'Leap 10 (Systems)' },
];

/**
 * 14 Günlük Kayan Pencere (Sliding Window) ve Çakışma Önleyici (Deduplication) ile
 * bildirim planı üretir. Saf matematiksel fonksiyondur, kolayca test edilebilir.
 */
export function buildCareNotificationPlan(
  baby: BabyProfileData,
  settings: NotificationSettings,
  referenceDate: Date = new Date(),
  windowDays: number = 14
): CareNotificationPlanItem[] {
  const items: CareNotificationPlanItem[] = [];
  const lang = normalizeCareLang(baby.lang || settings.lang);
  const defaultBabyName = lang === 'en' ? 'Your Baby' : 'Bebeğiniz';
  const rawName = baby.babyName && baby.babyName.trim();
  const babyName =
    rawName && !(lang === 'en' && (rawName === 'Bebeğim' || rawName === 'Bebeğiniz'))
      ? rawName
      : defaultBabyName;

  // Doğum tarihi kontrolü
  let birthDate: Date | null = null;
  if (baby.babyBdate) {
    const parsed = new Date(baby.babyBdate);
    if (!isNaN(parsed.getTime()) && parsed.getTime() <= referenceDate.getTime()) {
      birthDate = parsed;
    }
  }

  const windowStart = new Date(referenceDate);
  const windowEnd = new Date(referenceDate);
  windowEnd.setDate(windowEnd.getDate() + windowDays);

  // Gün gün gruplandırma haritası (YYYY-MM-DD -> item)
  const dayPlanMap = new Map<string, CareNotificationPlanItem>();

  const formatDateKey = (d: Date): string => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  // 1. AŞI BİLDİRİMLERİ (Öncelik: 1 - En Yüksek)
  if (settings.vaccineEnabled && birthDate) {
    for (const v of VACCINE_MILESTONES) {
      const milestoneDate = new Date(birthDate.getTime() + v.day * 24 * 60 * 60 * 1000);

      // 3 Gün Önce Hatırlatıcı (Sabah 10:30)
      const notify3DaysBefore = new Date(milestoneDate);
      notify3DaysBefore.setDate(notify3DaysBefore.getDate() - 3);
      notify3DaysBefore.setHours(10, 30, 0, 0);

      if (notify3DaysBefore >= windowStart && notify3DaysBefore <= windowEnd) {
        const key = formatDateKey(notify3DaysBefore);
        dayPlanMap.set(key, {
          id: `vaccine-3d-${v.month}m-${key}`,
          date: notify3DaysBefore,
          title:
            lang === 'en'
              ? `💉 Upcoming Vaccine Time for ${babyName}`
              : `💉 ${babyName} için Aşı Zamanı Yaklaşıyor`,
          body:
            lang === 'en'
              ? `Don't forget to check your pediatric appointment for Month ${v.month} immunizations. Mishil is right by your side.`
              : `${v.month}. ay aşıları için aile sağlığı merkezinden randevunuzu kontrol etmeyi unutmayın. Mışıl her an yanınızda.`,
          type: 'VACCINE',
          priority: 1,
        });
      }

      // 1 Gün Önce Hatırlatıcı (Sabah 10:30)
      const notify1DayBefore = new Date(milestoneDate);
      notify1DayBefore.setDate(notify1DayBefore.getDate() - 1);
      notify1DayBefore.setHours(10, 30, 0, 0);

      if (notify1DayBefore >= windowStart && notify1DayBefore <= windowEnd) {
        const key = formatDateKey(notify1DayBefore);
        const vLabel = lang === 'en' ? v.labelEn : v.label;
        dayPlanMap.set(key, {
          id: `vaccine-1d-${v.month}m-${key}`,
          date: notify1DayBefore,
          title:
            lang === 'en'
              ? `💉 Tomorrow is Vaccine Day for ${babyName}`
              : `💉 Yarın ${babyName} için Aşı Günü`,
          body:
            lang === 'en'
              ? `It's time for ${vLabel}. If your baby feels fussy after the visit, Mishil's soothing womb and shushing sounds are ready.`
              : `${vLabel} zamanı geldi. Aşı sonrası huzursuzluk olursa Mışıl'ın sakinleştirici pışpışlama sesleri hazır.`,
          type: 'VACCINE',
          priority: 1,
        });
      }
    }
  }

  // 2. BÜYÜME SIÇRAMASI / ATAK HAFTASI BİLDİRİMLERİ (Öncelik: 2)
  if (settings.leapWeeksEnabled && birthDate) {
    for (const leap of LEAP_WEEKS) {
      const leapStartDate = new Date(birthDate.getTime() + leap.week * 7 * 24 * 60 * 60 * 1000);
      leapStartDate.setHours(10, 30, 0, 0);

      if (leapStartDate >= windowStart && leapStartDate <= windowEnd) {
        const key = formatDateKey(leapStartDate);
        const leapTitle = lang === 'en' ? leap.titleEn : leap.title;
        // O günde aşı bildirimi yoksa sıçrama bildirimi yerleşir
        if (!dayPlanMap.has(key)) {
          dayPlanMap.set(key, {
            id: `leap-${leap.week}w-${key}`,
            date: leapStartDate,
            title:
              lang === 'en'
                ? `⚡ Week ${leap.week} Wonder Leap for ${babyName}`
                : `⚡ ${babyName} için ${leap.week}. Hafta Büyüme Sıçraması`,
            body:
              lang === 'en'
                ? `${leapTitle} has begun! Extra fussiness and shorter naps are completely normal right now. Our calming sounds are here to help.`
                : `${leapTitle} dönemi başladı! Bu günlerde uyku direnci ve huysuzluk çok normaldir. Sakinleştirici seslerimizle yanındayız.`,
            type: 'LEAP',
            priority: 2,
          });
        }
      }
    }
  }

  // 3. AKŞAM RUTİN / "UYUDU MU?" BİLDİRİMİ (Öncelik: 3)
  if (settings.routineSleepEnabled) {
    const [hourStr, minuteStr] = (settings.routineTime || '20:30').split(':');
    const routineHour = parseInt(hourStr || '20', 10);
    const routineMinute = parseInt(minuteStr || '30', 10);

    for (let dayOffset = 0; dayOffset < windowDays; dayOffset++) {
      const targetDay = new Date(referenceDate);
      targetDay.setDate(targetDay.getDate() + dayOffset);
      targetDay.setHours(routineHour, routineMinute, 0, 0);

      // Geçmiş saatleri atla
      if (targetDay <= referenceDate) continue;

      const key = formatDateKey(targetDay);
      // O günde aşı ya da atak bildirimi yoksa rutin kontrol bildirimi yerleşir
      if (!dayPlanMap.has(key)) {
        dayPlanMap.set(key, {
          id: `routine-sleep-${key}`,
          date: targetDay,
          title:
            lang === 'en'
              ? `🌙 Is ${babyName} sleeping peacefully?`
              : `🌙 ${babyName} mışıl mışıl uyudu mu?`,
          body:
            lang === 'en'
              ? `If settling is tough tonight, you can start womb and rhythmic shushing sounds with a single tap.`
              : `Uykuya dalmakta zorlanıyorsa, pışpışlama ve anne karnı seslerini tek dokunuşla başlatabilirsiniz.`,
          type: 'ROUTINE_SLEEP',
          priority: 3,
        });
      }
    }
  }

  // Tarihe göre sırala
  for (const item of dayPlanMap.values()) {
    items.push(item);
  }
  items.sort((a, b) => a.date.getTime() - b.date.getTime());

  // Güvenlik tavanı: iOS 64 limitine yaklaşmamak için maksimum windowDays kadar bildirim döner
  return items.slice(0, windowDays);
}

/**
 * AsyncStorage üzerinden bildirim ayarlarını okur.
 */
export async function getStoredNotificationSettings(): Promise<NotificationSettings> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY_NOTIFICATION_SETTINGS);
    if (raw) {
      return { ...DEFAULT_NOTIFICATION_SETTINGS, ...JSON.parse(raw) };
    }
  } catch (err) {
    console.warn('[CareNotification] Settings okunamadı:', err);
  }
  return DEFAULT_NOTIFICATION_SETTINGS;
}

/**
 * Bildirim ayarlarını kaydeder.
 */
export async function saveStoredNotificationSettings(
  settings: Partial<NotificationSettings>
): Promise<NotificationSettings> {
  const current = await getStoredNotificationSettings();
  const updated = { ...current, ...settings };
  try {
    await AsyncStorage.setItem(STORAGE_KEY_NOTIFICATION_SETTINGS, JSON.stringify(updated));
  } catch (err) {
    console.warn('[CareNotification] Settings kaydedilemedi:', err);
  }
  return updated;
}

/**
 * 14 Günlük Kayan Pencere Bildirimlerini OS Takvimine Senkronize Eder.
 * Eski planlanmış care bildirimlerini temizler ve yeni listeyi rezerve eder.
 */
export async function syncCareNotifications(
  baby: BabyProfileData,
  customSettings?: NotificationSettings
): Promise<{ scheduledCount: number; scheduledItems: CareNotificationPlanItem[] }> {
  if (Platform.OS === 'web') {
    return { scheduledCount: 0, scheduledItems: [] };
  }

  try {
    const settings = customSettings || (await getStoredNotificationSettings());
    const plan = buildCareNotificationPlan(baby, settings, new Date(), 14);

    // Bildirim izinlerini kontrol et
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      return { scheduledCount: 0, scheduledItems: [] };
    }

    // Mevcut planlanmış bildirimleri listele ve sadece MISIL_CARE_NOTIFICATION olanları iptal et
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    for (const notif of scheduled) {
      const data = notif.content.data as any;
      if (data && data.isMishilCareNotification) {
        await Notifications.cancelScheduledNotificationAsync(notif.identifier).catch(() => {});
      }
    }

    // Yeni planı OS kuyruğuna rezerve et
    let count = 0;
    for (const item of plan) {
      try {
        await Notifications.scheduleNotificationAsync({
          content: {
            title: item.title,
            body: item.body,
            sound: true,
            data: {
              isMishilCareNotification: true,
              careType: item.type,
              careId: item.id,
            },
          },
          trigger: {
            type: Notifications.SchedulableTriggerInputTypes.DATE,
            date: item.date,
          },
        });
        count++;
      } catch (scheduleErr) {
        console.warn(`[CareNotification] Planlanamadı (${item.id}):`, scheduleErr);
      }
    }

    return { scheduledCount: count, scheduledItems: plan };
  } catch (err) {
    console.warn('[CareNotification] syncCareNotifications hatası:', err);
    return { scheduledCount: 0, scheduledItems: [] };
  }
}
