import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const TOKEN_KEY = 'mishil_auth_token';
const ACTIVE_BABY_KEY = 'mishil_active_baby_id';
const OFFLINE_QUEUE_KEY = 'mishil_offline_routines_queue';
export const DEVICE_QUOTAS_KEY = 'mishil_device_quotas_v1';
export const APP_LANG_KEY = 'mishil_lang';
export type AppLang = 'tr' | 'en' | 'de';

export interface DeviceFreemiumQuotas {
  onboardedOnce: boolean;
  firstSpotUsed: boolean;
  freeSoundUsed: boolean;
  freeSoundElapsedMs: number;
  freeCryUsed: boolean;
  freeDadiUsed: boolean;
}

const EMPTY_DEVICE_QUOTAS: DeviceFreemiumQuotas = {
  onboardedOnce: false,
  firstSpotUsed: false,
  freeSoundUsed: false,
  freeSoundElapsedMs: 0,
  freeCryUsed: false,
  freeDadiUsed: false,
};

function sanitizeDeviceQuotas(raw: any): DeviceFreemiumQuotas {
  if (!raw || typeof raw !== 'object') return { ...EMPTY_DEVICE_QUOTAS };
  const elapsedRaw = Number(raw.freeSoundElapsedMs);
  const elapsed = Number.isFinite(elapsedRaw)
    ? Math.max(0, Math.min(60000, Math.round(elapsedRaw)))
    : 0;
  const soundUsed = Boolean(raw.freeSoundUsed) || elapsed >= 60000;
  return {
    onboardedOnce: Boolean(raw.onboardedOnce),
    firstSpotUsed: Boolean(raw.firstSpotUsed),
    freeSoundUsed: soundUsed,
    freeSoundElapsedMs: soundUsed ? Math.max(elapsed, 60000) : elapsed,
    freeCryUsed: Boolean(raw.freeCryUsed),
    freeDadiUsed: Boolean(raw.freeDadiUsed),
  };
}

let deviceQuotaMutex: Promise<unknown> = Promise.resolve();

async function readDeviceQuotasSnapshot(): Promise<DeviceFreemiumQuotas> {
  let secureParsed: DeviceFreemiumQuotas = { ...EMPTY_DEVICE_QUOTAS };
  let asyncParsed: DeviceFreemiumQuotas = { ...EMPTY_DEVICE_QUOTAS };
  if (Platform.OS !== 'web') {
    try {
      const rawSec = await SecureStore.getItemAsync(DEVICE_QUOTAS_KEY);
      if (rawSec) secureParsed = sanitizeDeviceQuotas(JSON.parse(rawSec));
    } catch {}
  }
  try {
    const rawAsync = await AsyncStorage.getItem(DEVICE_QUOTAS_KEY);
    if (rawAsync) asyncParsed = sanitizeDeviceQuotas(JSON.parse(rawAsync));
  } catch {}
  const mergedElapsed = Math.max(secureParsed.freeSoundElapsedMs, asyncParsed.freeSoundElapsedMs);
  const mergedSoundUsed = secureParsed.freeSoundUsed || asyncParsed.freeSoundUsed || mergedElapsed >= 60000;
  return {
    onboardedOnce: secureParsed.onboardedOnce || asyncParsed.onboardedOnce,
    firstSpotUsed: secureParsed.firstSpotUsed || asyncParsed.firstSpotUsed,
    freeSoundUsed: mergedSoundUsed,
    freeSoundElapsedMs: mergedSoundUsed ? Math.max(mergedElapsed, 60000) : mergedElapsed,
    freeCryUsed: secureParsed.freeCryUsed || asyncParsed.freeCryUsed,
    freeDadiUsed: secureParsed.freeDadiUsed || asyncParsed.freeDadiUsed,
  };
}

export const storage = {
  // Secure JWT Token Operations
  async getToken(): Promise<string | null> {
    if (Platform.OS === 'web') {
      return AsyncStorage.getItem(TOKEN_KEY);
    }
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  },

  async setToken(token: string): Promise<void> {
    if (Platform.OS === 'web') {
      await AsyncStorage.setItem(TOKEN_KEY, token);
      return;
    }
    try {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
    } catch {
      await AsyncStorage.setItem(TOKEN_KEY, token);
    }
  },

  async removeToken(): Promise<void> {
    if (Platform.OS === 'web') {
      await AsyncStorage.removeItem(TOKEN_KEY);
      return;
    }
    try {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    } catch {
      await AsyncStorage.removeItem(TOKEN_KEY);
    }
  },

  // Active Baby ID
  async getActiveBabyId(): Promise<number | null> {
    const val = await AsyncStorage.getItem(ACTIVE_BABY_KEY);
    return val ? parseInt(val, 10) : null;
  },

  async setActiveBabyId(id: number): Promise<void> {
    await AsyncStorage.setItem(ACTIVE_BABY_KEY, id.toString());
  },

  // Offline Queue
  async getOfflineQueue<T>(): Promise<T[]> {
    try {
      const data = await AsyncStorage.getItem(OFFLINE_QUEUE_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  },

  async setOfflineQueue<T>(queue: T[]): Promise<void> {
    await AsyncStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
  },

  // App Language ('tr' | 'en' | 'de')
  async getAppLang(): Promise<AppLang | null> {
    try {
      const raw = await AsyncStorage.getItem(APP_LANG_KEY);
      if (!raw) return null;
      const clean = raw.trim().toLowerCase();
      if (clean.startsWith('tr')) return 'tr';
      if (clean.startsWith('de')) return 'de';
      if (clean.startsWith('en')) return 'en';
      return 'en';
    } catch {
      return null;
    }
  },

  async setAppLang(lang: AppLang): Promise<void> {
    try {
      const clean = (lang || '').trim().toLowerCase();
      const normalized: AppLang = clean.startsWith('tr') ? 'tr' : (clean.startsWith('de') ? 'de' : 'en');
      await AsyncStorage.setItem(APP_LANG_KEY, normalized);
    } catch {
      // Ignore storage write errors
    }
  },

  // Cihaz Bazlı Freemium Hak Kalkanı (iOS Keychain / Android EncryptedSharedPreferences)
  // Kişisel bebek/profil verisi içermez; yalnızca anonim boolean kota bitlerini tutar (Apple 5.1.1(v) uyumlu).
  async getDeviceQuotas(): Promise<DeviceFreemiumQuotas> {
    await deviceQuotaMutex.catch(() => {});
    return readDeviceQuotasSnapshot();
  },

  async mergeDeviceQuotas(patch: Partial<DeviceFreemiumQuotas>): Promise<DeviceFreemiumQuotas> {
    const runMerge = async (): Promise<DeviceFreemiumQuotas> => {
      const cur = await readDeviceQuotasSnapshot();
      const incoming = sanitizeDeviceQuotas(patch || {});
      const mergedElapsed = Math.max(cur.freeSoundElapsedMs, incoming.freeSoundElapsedMs);
      const mergedSoundUsed = cur.freeSoundUsed || incoming.freeSoundUsed || mergedElapsed >= 60000;
      const next: DeviceFreemiumQuotas = {
        onboardedOnce: cur.onboardedOnce || incoming.onboardedOnce,
        firstSpotUsed: cur.firstSpotUsed || incoming.firstSpotUsed,
        freeSoundUsed: mergedSoundUsed,
        freeSoundElapsedMs: mergedSoundUsed ? Math.max(mergedElapsed, 60000) : mergedElapsed,
        freeCryUsed: cur.freeCryUsed || incoming.freeCryUsed,
        freeDadiUsed: cur.freeDadiUsed || incoming.freeDadiUsed,
      };
      const serialized = JSON.stringify(next);
      if (Platform.OS !== 'web') {
        try {
          await SecureStore.setItemAsync(DEVICE_QUOTAS_KEY, serialized);
        } catch {}
      }
      try {
        await AsyncStorage.setItem(DEVICE_QUOTAS_KEY, serialized);
      } catch {}
      return next;
    };
    const queued = deviceQuotaMutex.then(runMerge, runMerge);
    deviceQuotaMutex = queued.then(() => undefined, () => undefined);
    return queued;
  },

  // Apple 5.1.1(v) Hesap ve Kişisel Veri Silme — profil/rutin verilerini siler, anonim cihaz kota bitlerini korur
  async clearPersonalAppData(): Promise<void> {
    await this.removeToken();
    const personalKeys = [
      '@mishil_baby_profile',
      '@mishil_onboarding_completed',
      ACTIVE_BABY_KEY,
      OFFLINE_QUEUE_KEY,
    ];
    try {
      if (typeof AsyncStorage.multiRemove === 'function') {
        await AsyncStorage.multiRemove(personalKeys);
      } else {
        await Promise.all(personalKeys.map((k) => AsyncStorage.removeItem(k)));
      }
    } catch {}
  },
};
