import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { AppLang } from '../../lib/storage';

export type CareLang = AppLang;
export const GENERIC_BABY_NAMES = new Set([
  'Bebeğim',
  'Bebeğiniz',
  'My Baby',
  'Your Baby',
  'Mein Baby',
  'Dein Baby',
  'Ihr Baby',
]);

export function normalizeCareLang(raw?: string | null): CareLang {
  if (!raw || typeof raw !== 'string') return 'tr';
  const clean = raw.trim().toLowerCase();
  if (!clean) return 'tr';
  if (clean.startsWith('tr')) return 'tr';
  if (clean.startsWith('de')) return 'de';
  return 'en';
}

export interface NotificationSettings {
  vaccineEnabled: boolean;
  routineSleepEnabled: boolean;
  leapWeeksEnabled: boolean;
  routineTime: string; // e.g. "20:30"
  lang?: CareLang;
  vaccineCountry?: string; // ISO-3166-1 alpha-2 (e.g. 'TR', 'DE', 'GB', 'US', 'CH', 'AZ', 'KZ')
}

export interface BabyProfileData {
  babyName?: string;
  babyBdate?: string; // YYYY-MM-DD
  lang?: CareLang | string;
  vaccineCountry?: string;
}

export interface VaccineMilestoneItem {
  day: number;
  month: number;
  label: string;
  labelEn: string;
  labelDe?: string;
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

// T.C. Sağlık Bakanlığı Çocukluk Dönemi Aşı Takvimi Kilometre Taşları (Varsayılan / TR)
export const VACCINE_MILESTONES: VaccineMilestoneItem[] = [
  { day: 30, month: 1, label: '1. Ay Aşıları (Hepatit B 2. doz)', labelEn: 'Month 1 Vaccines (Hepatitis B Dose 2)', labelDe: '1. Monat Impfungen (Hepatitis B 2. Dosis)' },
  { day: 60, month: 2, label: '2. Ay Aşıları (Verem/BCG, 5\'li Karma 1. doz, KPA 1. doz)', labelEn: 'Month 2 Vaccines (DTaP-IPV-Hib Dose 1, PCV13 Dose 1, BCG / Rotavirus per local schedule)', labelDe: '2. Monat Impfungen (Kombi-Impfung 1. Dosis, Pneumokokken 1. Dosis)' },
  { day: 120, month: 4, label: '4. Ay Aşıları (5\'li Karma 2. doz, KPA 2. doz)', labelEn: 'Month 4 Vaccines (DTaP-IPV-Hib Dose 2, PCV13 Dose 2)', labelDe: '4. Monat Impfungen (Kombi-Impfung 2. Dosis, Pneumokokken 2. Dosis)' },
  { day: 180, month: 6, label: '6. Ay Aşıları (Hepatit B 3. doz, 5\'li Karma 3. doz, Çocuk Felci)', labelEn: 'Month 6 Vaccines (Hepatitis B Dose 3, DTaP-IPV-Hib Dose 3)', labelDe: '6. Monat Impfungen (Hepatitis B 3. Dosis, Kombi-Impfung 3. Dosis)' },
  { day: 270, month: 9, label: '9. Ay Aşıları (Meningokok / Kızamık Kontrolü)', labelEn: 'Month 9 Vaccines (Meningococcal / Measles Checkup)', labelDe: '9. Monat Impfungen (Meningokokken- / Masern-Kontrolle)' },
  { day: 365, month: 12, label: '12. Ay Aşıları (KKK, Suçiçeği, KPA Pekiştirme)', labelEn: 'Month 12 Vaccines (MMR, Varicella, PCV13 Booster)', labelDe: '12. Monat Impfungen (MMR, Windpocken, Pneumokokken-Auffrischung)' },
  { day: 540, month: 18, label: '18. Ay Aşıları (5\'li Karma Pekiştirme, Çocuk Felci, Hepatit A 1. doz)', labelEn: 'Month 18 Vaccines (DTaP-IPV-Hib Booster, Hepatitis A Dose 1)', labelDe: '18. Monat Impfungen (Kombi-Auffrischung, Hepatitis A 1. Dosis)' },
  { day: 720, month: 24, label: '24. Ay Aşıları (Hepatit A 2. doz)', labelEn: 'Month 24 Vaccines (Hepatitis A Dose 2)', labelDe: '24. Monat Impfungen (Hepatitis A 2. Dosis)' },
];

export const VACCINE_MILESTONES_BY_PROTOCOL: Record<string, VaccineMilestoneItem[]> = {
  TR: VACCINE_MILESTONES,
  // ABD & Kanada (CDC / AAP / NACI): 1, 2, 4, 6, 12, 15, 18. Aylar
  US_CDC: [
    { day: 30, month: 1, label: '1. Ay Aşıları (Hepatit B 2. doz)', labelEn: 'Month 1 Vaccines (Hepatitis B Dose 2)', labelDe: '1. Monat Impfungen (Hepatitis B 2. Dosis)' },
    { day: 60, month: 2, label: '2. Ay Aşıları (DTaP, IPV, Hib, PCV, Rotavirüs 1. doz)', labelEn: 'Month 2 Vaccines (DTaP, IPV, Hib, PCV, Rotavirus Dose 1)', labelDe: '2. Monat Impfungen (DTaP, IPV, Hib, Pneumokokken, Rotaviren 1. Dosis)' },
    { day: 120, month: 4, label: '4. Ay Aşıları (DTaP, IPV, Hib, PCV, Rotavirüs 2. doz)', labelEn: 'Month 4 Vaccines (DTaP, IPV, Hib, PCV, Rotavirus Dose 2)', labelDe: '4. Monat Impfungen (DTaP, IPV, Hib, Pneumokokken, Rotaviren 2. Dosis)' },
    { day: 180, month: 6, label: '6. Ay Aşıları (DTaP, IPV, PCV, Rotavirüs, Hepatit B 3. doz, Grip)', labelEn: 'Month 6 Vaccines (DTaP, IPV, PCV, Rotavirus, HepB Dose 3, Flu)', labelDe: '6. Monat Impfungen (DTaP, IPV, Pneumokokken, Rotaviren, HepB 3. Dosis, Grippe)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (MMR, Suçiçeği, PCV Rapel, Hepatit A 1. doz)', labelEn: 'Month 12 Vaccines (MMR, Varicella, PCV Booster, Hepatitis A Dose 1)', labelDe: '12. Monat Impfungen (MMR, Windpocken, Pneumokokken-Auffrischung, Hepatitis A 1. Dosis)' },
    { day: 450, month: 15, label: '15. Ay Aşıları (DTaP Pekiştirme, Hib Pekiştirme)', labelEn: 'Month 15 Vaccines (DTaP Booster, Hib Booster)', labelDe: '15. Monat Impfungen (DTaP- & Hib-Auffrischung)' },
    { day: 540, month: 18, label: '18. Ay Aşıları (Hepatit A 2. doz)', labelEn: 'Month 18 Vaccines (Hepatitis A Dose 2)', labelDe: '18. Monat Impfungen (Hepatitis A 2. Dosis)' },
  ],
  // Birleşik Krallık & İrlanda (NHS / HSE): 2, 3, 4 ve 12. Aylar (8, 12, 16 Hafta)
  UK_NHS: [
    { day: 60, month: 2, label: '2. Ay / 8. Hafta Aşıları (6\'lı Karma 1. doz, Rotavirüs 1. doz, MenB 1. doz)', labelEn: '8-Week / Month 2 Vaccines (6-in-1 Dose 1, Rotavirus Dose 1, MenB Dose 1)', labelDe: '8. Woche / 2. Monat Impfungen (6-fach 1. Dosis, Rotaviren 1. Dosis, MenB 1. Dosis)' },
    { day: 90, month: 3, label: '3. Ay / 12. Hafta Aşıları (6\'lı Karma 2. doz, PCV 1. doz, Rotavirüs 2. doz)', labelEn: '12-Week / Month 3 Vaccines (6-in-1 Dose 2, PCV Dose 1, Rotavirus Dose 2)', labelDe: '12. Woche / 3. Monat Impfungen (6-fach 2. Dosis, Pneumokokken 1. Dosis, Rotaviren 2. Dosis)' },
    { day: 120, month: 4, label: '4. Ay / 16. Hafta Aşıları (6\'lı Karma 3. doz, MenB 2. doz)', labelEn: '16-Week / Month 4 Vaccines (6-in-1 Dose 3, MenB Dose 2)', labelDe: '16. Woche / 4. Monat Impfungen (6-fach 3. Dosis, MenB 2. Dosis)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (Hib/MenC, PCV Rapel, MMR 1. doz, MenB Rapel)', labelEn: 'Month 12 Vaccines (Hib/MenC, PCV Booster, MMR Dose 1, MenB Booster)', labelDe: '12. Monat Impfungen (Hib/MenC, Pneumokokken-Auffrischung, MMR 1. Dosis, MenB-Auffrischung)' },
  ],
  // Batı & Kuzey Avrupa / DACH (ECDC / STIKO / Österreichischer Impfplan 2+1 Şeması): 2, 4, 11, 12, 15. Aylar
  EU_2PLUS1: [
    { day: 60, month: 2, label: '2. Ay Aşıları (6\'lı Karma 1. doz, Pnömokok 1. doz, Rotavirüs 1. doz)', labelEn: 'Month 2 Vaccines (6-in-1 Hexavalent Dose 1, PCV Dose 1, Rotavirus Dose 1)', labelDe: '2. Monat Impfungen (6-fach-Impfung 1. Dosis, Pneumokokken 1. Dosis, Rotaviren 1. Dosis)' },
    { day: 120, month: 4, label: '4. Ay Aşıları (6\'lı Karma 2. doz, Pnömokok 2. doz, Rotavirüs 2. doz)', labelEn: 'Month 4 Vaccines (6-in-1 Hexavalent Dose 2, PCV Dose 2, Rotavirus Dose 2)', labelDe: '4. Monat Impfungen (6-fach-Impfung 2. Dosis, Pneumokokken 2. Dosis, Rotaviren 2. Dosis)' },
    { day: 330, month: 11, label: '11. Ay Aşıları (6\'lı Karma 3. doz, Pnömokok Rapel, MMR 1. doz, Suçiçeği 1. doz)', labelEn: 'Month 11 Vaccines (6-in-1 Dose 3, PCV Booster, MMR Dose 1, Varicella Dose 1)', labelDe: '11. Monat Impfungen (6-fach 3. Dosis, Pneumokokken-Auffrischung, MMR 1. Dosis, Windpocken 1. Dosis)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (Meningokok C / B)', labelEn: 'Month 12 Vaccines (Meningococcal C / B)', labelDe: '12. Monat Impfungen (Meningokokken C / B)' },
    { day: 450, month: 15, label: '15. Ay Aşıları (MMR 2. doz, Suçiçeği 2. doz)', labelEn: 'Month 15 Vaccines (MMR Dose 2, Varicella Dose 2)', labelDe: '15. Monat Impfungen (MMR 2. Dosis, Windpocken 2. Dosis)' },
  ],
  // İsviçre (BAG / EKIF): 2, 4, 9, 12. Aylar
  CH_BAG: [
    { day: 60, month: 2, label: '2. Ay Aşıları (6\'lı Karma 1. doz, PCV 1. doz, Rotavirüs 1. doz)', labelEn: 'Month 2 Vaccines (6-in-1 Dose 1, PCV Dose 1, Rotavirus Dose 1)', labelDe: '2. Monat BAG-Impfungen (6-fach-Impfung 1. Dosis, Pneumokokken 1. Dosis, Rotaviren 1. Dosis)' },
    { day: 120, month: 4, label: '4. Ay Aşıları (6\'lı Karma 2. doz, PCV 2. doz, Rotavirüs 2. doz)', labelEn: 'Month 4 Vaccines (6-in-1 Dose 2, PCV Dose 2, Rotavirus Dose 2)', labelDe: '4. Monat BAG-Impfungen (6-fach-Impfung 2. Dosis, Pneumokokken 2. Dosis, Rotaviren 2. Dosis)' },
    { day: 270, month: 9, label: '9. Ay Aşıları (MMR 1. doz)', labelEn: 'Month 9 Vaccines (MMR Dose 1)', labelDe: '9. Monat BAG-Impfungen (MMR 1. Dosis)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (6\'lı Karma 3. doz, PCV Rapel, MMR 2. doz, Suçiçeği, MenACWY)', labelEn: 'Month 12 Vaccines (6-in-1 Dose 3, PCV Booster, MMR Dose 2, Varicella, MenACWY)', labelDe: '12. Monat BAG-Impfungen (6-fach 3. Dosis, Pneumokokken-Booster, MMR 2. Dosis, Windpocken, MenACWY)' },
  ],
  // Türk Devletleri & BDT (AZ, KZ, UZ, KG, TM, GE, RU, UA): 2, 3, 4, 6, 12, 18. Aylar
  CIS_TURKIC: [
    { day: 60, month: 2, label: '2. Ay Aşıları (Karma Aşı 1. doz, Pnömokok 1. doz, Rotavirüs 1. doz)', labelEn: 'Month 2 Vaccines (Hexa/Pentavalent Dose 1, PCV Dose 1, Rotavirus Dose 1)', labelDe: '2. Monat Impfungen (Kombi-Impfung 1. Dosis, Pneumokokken 1. Dosis, Rotaviren 1. Dosis)' },
    { day: 90, month: 3, label: '3. Ay Aşıları (Karma Aşı 2. doz, Rotavirüs 2. doz)', labelEn: 'Month 3 Vaccines (Hexa/Pentavalent Dose 2, Rotavirus Dose 2)', labelDe: '3. Monat Impfungen (Kombi-Impfung 2. Dosis, Rotaviren 2. Dosis)' },
    { day: 120, month: 4, label: '4. Ay Aşıları (Karma Aşı 3. doz, Pnömokok 2. doz)', labelEn: 'Month 4 Vaccines (Hexa/Pentavalent Dose 3, PCV Dose 2)', labelDe: '4. Monat Impfungen (Kombi-Impfung 3. Dosis, Pneumokokken 2. Dosis)' },
    { day: 180, month: 6, label: '6. Ay Aşıları (Hepatit B 3. doz, Çocuk Felci)', labelEn: 'Month 6 Vaccines (Hepatitis B Dose 3, Polio)', labelDe: '6. Monat Impfungen (Hepatitis B 3. Dosis, Polio)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (KKK/MMR, Suçiçeği, Pnömokok Pekiştirme)', labelEn: 'Month 12 Vaccines (MMR, Varicella, PCV Booster)', labelDe: '12. Monat Impfungen (MMR, Windpocken, Pneumokokken-Auffrischung)' },
    { day: 540, month: 18, label: '18. Ay Aşıları (Karma Pekiştirme, Hepatit A)', labelEn: 'Month 18 Vaccines (DTP-IPV-Hib Booster, Hepatitis A)', labelDe: '18. Monat Impfungen (Kombi-Auffrischung, Hepatitis A)' },
  ],
  // Avustralya & Yeni Zelanda (NIP): 2, 4, 6, 12, 18. Aylar
  AU_NIP: [
    { day: 60, month: 2, label: '2. Ay Aşıları (6\'lı Karma 1. doz, PCV 1. doz, Rotavirüs 1. doz, MenB 1. doz)', labelEn: 'Month 2 Vaccines (6-in-1 Dose 1, PCV Dose 1, Rotavirus Dose 1, MenB Dose 1)', labelDe: '2. Monat Impfungen (6-fach 1. Dosis, Pneumokokken 1. Dosis, Rotaviren 1. Dosis, MenB 1. Dosis)' },
    { day: 120, month: 4, label: '4. Ay Aşıları (6\'lı Karma 2. doz, PCV 2. doz, Rotavirüs 2. doz, MenB 2. doz)', labelEn: 'Month 4 Vaccines (6-in-1 Dose 2, PCV Dose 2, Rotavirus Dose 2, MenB Dose 2)', labelDe: '4. Monat Impfungen (6-fach 2. Dosis, Pneumokokken 2. Dosis, Rotaviren 2. Dosis, MenB 2. Dosis)' },
    { day: 180, month: 6, label: '6. Ay Aşıları (6\'lı Karma 3. doz)', labelEn: 'Month 6 Vaccines (6-in-1 Dose 3)', labelDe: '6. Monat Impfungen (6-fach 3. Dosis)' },
    { day: 365, month: 12, label: '12. Ay Aşıları (MMR, MenACWY, PCV Rapel, MenB Rapel)', labelEn: 'Month 12 Vaccines (MMR, MenACWY, PCV Booster, MenB Booster)', labelDe: '12. Monat Impfungen (MMR, MenACWY, Pneumokokken- & MenB-Auffrischung)' },
    { day: 540, month: 18, label: '18. Ay Aşıları (MMRV, DTPa, Hib Pekiştirme)', labelEn: 'Month 18 Vaccines (MMRV, DTPa, Hib Booster)', labelDe: '18. Monat Impfungen (MMRV, DTPa, Hib-Auffrischung)' },
  ],
};

const COUNTRY_TO_NOTIFICATION_PROTOCOL: Record<string, string> = {
  TR: 'TR', CY: 'TR',
  US: 'US_CDC', CA: 'US_CDC', PR: 'US_CDC',
  GB: 'UK_NHS', UK: 'UK_NHS', IE: 'UK_NHS',
  CH: 'CH_BAG', LI: 'CH_BAG',
  DE: 'EU_2PLUS1', AT: 'EU_2PLUS1', NL: 'EU_2PLUS1', BE: 'EU_2PLUS1', LU: 'EU_2PLUS1',
  FR: 'EU_2PLUS1', IT: 'EU_2PLUS1', ES: 'EU_2PLUS1', PT: 'EU_2PLUS1', GR: 'EU_2PLUS1',
  SE: 'EU_2PLUS1', NO: 'EU_2PLUS1', DK: 'EU_2PLUS1', FI: 'EU_2PLUS1', IS: 'EU_2PLUS1',
  PL: 'EU_2PLUS1', CZ: 'EU_2PLUS1', SK: 'EU_2PLUS1', HU: 'EU_2PLUS1', SI: 'EU_2PLUS1',
  EE: 'EU_2PLUS1', LV: 'EU_2PLUS1', LT: 'EU_2PLUS1', MT: 'EU_2PLUS1',
  AZ: 'CIS_TURKIC', KZ: 'CIS_TURKIC', UZ: 'CIS_TURKIC', KG: 'CIS_TURKIC', TM: 'CIS_TURKIC',
  GE: 'CIS_TURKIC', RU: 'CIS_TURKIC', UA: 'CIS_TURKIC', BY: 'CIS_TURKIC', AM: 'CIS_TURKIC', TJ: 'CIS_TURKIC',
  AU: 'AU_NIP', NZ: 'AU_NIP',
};

export function getVaccineMilestonesForCountry(countryCode?: string | null): VaccineMilestoneItem[] {
  if (!countryCode || typeof countryCode !== 'string') return VACCINE_MILESTONES;
  const clean = countryCode.trim().toUpperCase();
  const protoKey = COUNTRY_TO_NOTIFICATION_PROTOCOL[clean] || 'TR';
  return VACCINE_MILESTONES_BY_PROTOCOL[protoKey] || VACCINE_MILESTONES;
}

// Wonder Weeks (Büyüme Sıçraması / Atak Haftaları - Doğum gününden sonraki haftalar)
export const LEAP_WEEKS = [
  { week: 5, title: '1. Sıçrama (Değişen Duyular)', titleEn: 'Leap 1 (Changing Sensations)', titleDe: '1. Sprung (Sinneseindrücke)' },
  { week: 8, title: '2. Sıçrama (Oluşumlar & Desenler)', titleEn: 'Leap 2 (Patterns)', titleDe: '2. Sprung (Muster & Strukturen)' },
  { week: 12, title: '3. Sıçrama (Yumuşak Geçişler)', titleEn: 'Leap 3 (Smooth Transitions)', titleDe: '3. Sprung (Sanfte Übergänge)' },
  { week: 19, title: '4. Sıçrama (4. Ay Uyku Gerilemesi)', titleEn: 'Leap 4 (Events & 4-Month Sleep Regression)', titleDe: '4. Sprung (Ereignisse & 4-Monats-Schlafregression)' },
  { week: 26, title: '5. Sıçrama (İlişkiler Dünyası)', titleEn: 'Leap 5 (Relationships)', titleDe: '5. Sprung (Zusammenhänge & Distanz)' },
  { week: 37, title: '6. Sıçrama (Kategoriler)', titleEn: 'Leap 6 (Categories)', titleDe: '6. Sprung (Kategorien)' },
  { week: 46, title: '7. Sıçrama (Dizilimler)', titleEn: 'Leap 7 (Sequences)', titleDe: '7. Sprung (Reihenfolgen)' },
  { week: 55, title: '8. Sıçrama (Programlar)', titleEn: 'Leap 8 (Programs)', titleDe: '8. Sprung (Programme)' },
  { week: 64, title: '9. Sıçrama (İlkeler)', titleEn: 'Leap 9 (Principles)', titleDe: '9. Sprung (Prinzipien)' },
  { week: 75, title: '10. Sıçrama (Sistemler)', titleEn: 'Leap 10 (Systems)', titleDe: '10. Sprung (Systeme)' },
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
  const defaultBabyName = lang === 'de' ? 'Dein Baby' : (lang === 'en' ? 'Your Baby' : 'Bebeğiniz');
  const rawName = baby.babyName && baby.babyName.trim();
  const babyName = rawName && !GENERIC_BABY_NAMES.has(rawName) ? rawName : defaultBabyName;

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
    const defaultCountryByLang = lang === 'de' ? 'DE' : 'TR';
    const rawCountry = (baby.vaccineCountry || settings.vaccineCountry || defaultCountryByLang).trim().toUpperCase();
    const isTrClinic = rawCountry === 'TR' || rawCountry === 'CY';
    const activeMilestones = getVaccineMilestonesForCountry(rawCountry);
    for (const v of activeMilestones) {
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
            lang === 'de'
              ? `💉 Impftermin für ${babyName} steht bevor`
              : lang === 'en'
                ? `💉 Upcoming Vaccine Time for ${babyName}`
                : `💉 ${babyName} için Aşı Zamanı Yaklaşıyor`,
          body:
            lang === 'de'
              ? `Denke daran, den Kinderarzttermin für die Impfungen im ${v.month}. Monat zu prüfen. Mışıl begleitet euch jederzeit.`
              : lang === 'en'
                ? `Don't forget to check your pediatric appointment for Month ${v.month} immunizations. Mishil is right by your side.`
                : isTrClinic
                  ? `${v.month}. ay aşıları için aile sağlığı merkezinden randevunuzu kontrol etmeyi unutmayın. Mışıl her an yanınızda.`
                  : `${v.month}. ay aşıları için çocuk doktorunuzdan veya kliniğinizden randevunuzu kontrol etmeyi unutmayın. Mışıl her an yanınızda.`,
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
        const vLabel = lang === 'de' ? (v.labelDe || v.labelEn) : (lang === 'en' ? v.labelEn : v.label);
        dayPlanMap.set(key, {
          id: `vaccine-1d-${v.month}m-${key}`,
          date: notify1DayBefore,
          title:
            lang === 'de'
              ? `💉 Morgen ist Impftag für ${babyName}`
              : lang === 'en'
                ? `💉 Tomorrow is Vaccine Day for ${babyName}`
                : `💉 Yarın ${babyName} için Aşı Günü`,
          body:
            lang === 'de'
              ? `Zeit für: ${vLabel}. Falls ${babyName} danach unruhig ist, stehen die beruhigenden Mutterleibs- und Sch-Sch-Klänge bereit.`
              : lang === 'en'
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
        const leapTitle = lang === 'de' ? (leap.titleDe || leap.titleEn) : (lang === 'en' ? leap.titleEn : leap.title);
        // O günde aşı bildirimi yoksa sıçrama bildirimi yerleşir
        if (!dayPlanMap.has(key)) {
          dayPlanMap.set(key, {
            id: `leap-${leap.week}w-${key}`,
            date: leapStartDate,
            title:
              lang === 'de'
                ? `⚡ Woche ${leap.week}: Entwicklungssprung bei ${babyName}`
                : lang === 'en'
                  ? `⚡ Week ${leap.week} Wonder Leap for ${babyName}`
                  : `⚡ ${babyName} için ${leap.week}. Hafta Büyüme Sıçraması`,
            body:
              lang === 'de'
                ? `${leapTitle} hat begonnen! Mehr Nähebedürfnis und kürzere Schläfchen sind jetzt völlig normal. Unsere Beruhigungsklänge helfen euch.`
                : lang === 'en'
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
    const rawTime = String(settings.routineTime || '20:30').trim();
    const timeMatch = /^(\d{1,2}):(\d{2})$/.exec(rawTime);
    const parsedHour = timeMatch ? parseInt(timeMatch[1], 10) : NaN;
    const parsedMinute = timeMatch ? parseInt(timeMatch[2], 10) : NaN;
    const isValidTime =
      Number.isInteger(parsedHour) &&
      Number.isInteger(parsedMinute) &&
      parsedHour >= 0 &&
      parsedHour <= 23 &&
      parsedMinute >= 0 &&
      parsedMinute <= 59;
    const routineHour = isValidTime ? parsedHour : 20;
    const routineMinute = isValidTime ? parsedMinute : 30;

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
            lang === 'de'
              ? `🌙 Schläft ${babyName} schon friedlich?`
              : lang === 'en'
                ? `🌙 Is ${babyName} sleeping peacefully?`
                : `🌙 ${babyName} mışıl mışıl uyudu mu?`,
          body:
            lang === 'de'
              ? `Falls das Einschlafen heute Abend schwerfällt, kannst du Mutterleibs- und Sch-Sch-Klänge mit einem Tippen starten.`
              : lang === 'en'
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
