import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface NotificationSettings {
  vaccineEnabled: boolean;
  routineSleepEnabled: boolean;
  leapWeeksEnabled: boolean;
  routineTime: string; // e.g. "20:30"
}

export interface BabyProfileData {
  babyName?: string;
  babyBdate?: string; // YYYY-MM-DD
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
};

export const STORAGE_KEY_NOTIFICATION_SETTINGS = '@mishil_notification_settings';

// T.C. Sağlık Bakanlığı Çocukluk Dönemi Aşı Takvimi Kilometre Taşları (Doğum gününe göre gün cinsinden)
export const VACCINE_MILESTONES = [
  { day: 30, month: 1, label: '1. Ay Aşıları (Hepatit B 2. doz)' },
  { day: 60, month: 2, label: '2. Ay Aşıları (Verem/BCG, 5\'li Karma 1. doz, KPA 1. doz)' },
  { day: 120, month: 4, label: '4. Ay Aşıları (5\'li Karma 2. doz, KPA 2. doz)' },
  { day: 180, month: 6, label: '6. Ay Aşıları (Hepatit B 3. doz, 5\'li Karma 3. doz, Çocuk Felci)' },
  { day: 270, month: 9, label: '9. Ay Aşıları (Kızamık)' },
  { day: 365, month: 12, label: '12. Ay Aşıları (KKK, Suçiçeği, KPA Pekiştirme)' },
  { day: 540, month: 18, label: '18. Ay Aşıları (5\'li Karma Pekiştirme, Çocuk Felci, Hepatit A 1. doz)' },
  { day: 720, month: 24, label: '24. Ay Aşıları (Hepatit A 2. doz)' },
];

// Wonder Weeks (Büyüme Sıçraması / Atak Haftaları - Doğum gününden sonraki haftalar)
export const LEAP_WEEKS = [
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
  const babyName = (baby.babyName && baby.babyName.trim()) || 'Bebeğiniz';

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
          title: `💉 ${babyName} için Aşı Zamanı Yaklaşıyor`,
          body: `${v.month}. ay aşıları için aile sağlığı merkezinden randevunuzu kontrol etmeyi unutmayın. Mışıl her an yanınızda.`,
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
        dayPlanMap.set(key, {
          id: `vaccine-1d-${v.month}m-${key}`,
          date: notify1DayBefore,
          title: `💉 Yarın ${babyName} için Aşı Günü`,
          body: `${v.label} zamanı geldi. Aşı sonrası huzursuzluk olursa Mışıl'ın sakinleştirici pışpışlama sesleri hazır.`,
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
        // O günde aşı bildirimi yoksa sıçrama bildirimi yerleşir
        if (!dayPlanMap.has(key)) {
          dayPlanMap.set(key, {
            id: `leap-${leap.week}w-${key}`,
            date: leapStartDate,
            title: `⚡ ${babyName} için ${leap.week}. Hafta Büyüme Sıçraması`,
            body: `${leap.title} dönemi başladı! Bu günlerde uyku direnci ve huysuzluk çok normaldir. Sakinleştirici seslerimizle yanındayız.`,
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
          title: `🌙 ${babyName} mışıl mışıl uyudu mu?`,
          body: `Uykuya dalmakta zorlanıyorsa, pışpışlama ve anne karnı seslerini tek dokunuşla başlatabilirsiniz.`,
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
