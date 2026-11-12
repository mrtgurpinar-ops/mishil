import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import * as MishilLockScreen from '../../modules/mishil-lockscreen/src';

const STORAGE_KEY = '@mishil_live_sleep_native';
const MAX_SLEEP_AGE_MS = 16 * 3600000;

export interface NativeLiveSleepState {
  active: boolean;
  startEpochMs: number;
  sleepLabel: string;
  subtitle: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
  lang: 'tr' | 'en' | 'de';
}

const defaultState: NativeLiveSleepState = {
  active: false,
  startEpochMs: 0,
  sleepLabel: '',
  subtitle: '',
  lang: 'tr',
};

let hasPromptedNotificationPermission = false;

async function readState(): Promise<NativeLiveSleepState> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaultState };
    const parsed = JSON.parse(raw);
    return { ...defaultState, ...parsed };
  } catch {
    return { ...defaultState };
  }
}

async function writeState(state: NativeLiveSleepState): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {}
}

async function clearState(): Promise<void> {
  try {
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {}
}

async function maybeRequestNotificationPermission(): Promise<void> {
  if (Platform.OS !== 'android' || Number(Platform.Version) < 33 || hasPromptedNotificationPermission) return;
  hasPromptedNotificationPermission = true;
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    if (existingStatus !== 'granted') {
      await Notifications.requestPermissionsAsync();
    }
  } catch {
    // İzin reddedilse bile canlı uyku akışını bloklamaz
  }
}

export async function startNativeLiveSleep(options: {
  startEpochMs: number;
  sleepLabel: string;
  subtitle?: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
  lang?: 'tr' | 'en' | 'de';
}): Promise<void> {
  if (!MishilLockScreen.isNativeLockScreenAvailable()) return;
  await maybeRequestNotificationPermission();

  const state: NativeLiveSleepState = {
    active: true,
    startEpochMs: options.startEpochMs,
    sleepLabel: options.sleepLabel,
    subtitle: options.subtitle || '',
    babyName: options.babyName,
    showBabyNameOnLockScreen: options.showBabyNameOnLockScreen,
    lang: options.lang || 'tr',
  };
  await writeState(state);
  await MishilLockScreen.startLiveSleep({
    startEpochMs: options.startEpochMs,
    sleepLabel: options.sleepLabel,
    subtitle: options.subtitle,
    babyName: options.babyName,
    showBabyNameOnLockScreen: options.showBabyNameOnLockScreen,
    lang: options.lang,
  });
}

export async function updateNativeLiveSleep(options: {
  startEpochMs: number;
  sleepLabel?: string;
  subtitle?: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
}): Promise<void> {
  if (!MishilLockScreen.isNativeLockScreenAvailable()) return;
  const current = await readState();
  if (!current.active) return;

  const next: NativeLiveSleepState = {
    ...current,
    startEpochMs: options.startEpochMs,
    sleepLabel: options.sleepLabel ?? current.sleepLabel,
    subtitle: options.subtitle ?? current.subtitle,
    babyName: options.babyName ?? current.babyName,
    showBabyNameOnLockScreen: options.showBabyNameOnLockScreen ?? current.showBabyNameOnLockScreen,
  };
  await writeState(next);
  const updated = await MishilLockScreen.updateLiveSleep(options);
  if (!updated) {
    // iOS 8 saat sistem sınırı veya servis yeniden başlatması nedeniyle aktivite düşmüşse aynı başlangıç saatiyle yeniden kur
    await MishilLockScreen.startLiveSleep({
      startEpochMs: next.startEpochMs,
      sleepLabel: next.sleepLabel,
      subtitle: next.subtitle,
      babyName: next.babyName,
      showBabyNameOnLockScreen: next.showBabyNameOnLockScreen,
      lang: next.lang,
    });
  }
}

export async function stopNativeLiveSleep(): Promise<void> {
  await clearState();
  if (!MishilLockScreen.isNativeLockScreenAvailable()) return;
  await MishilLockScreen.stopLiveSleep();
}

/**
 * Uygulama açılışında ve ön plana (AppState === 'active') geçişte:
 * - 16 saatten eski veya `active: false` yetim Live Activity'leri temizler,
 * - Aktif (<16s) uykularda iOS 8 saatlik ActivityKit penceresi dolmuş/düşmüş veya Android bildirimi kaybolmuşsa
 *   orijinal `startEpochMs` korunarak kesintisiz yeniden canlandırır.
 */
export async function reconcileNativeLiveSleepOnLaunch(): Promise<void> {
  if (!MishilLockScreen.isNativeLockScreenAvailable()) return;
  const state = await readState();
  if (!state.active) {
    await MishilLockScreen.stopLiveSleep();
    return;
  }
  const age = Date.now() - state.startEpochMs;
  if (!state.startEpochMs || age > MAX_SLEEP_AGE_MS) {
    await clearState();
    await MishilLockScreen.stopLiveSleep();
    return;
  }
  if (typeof MishilLockScreen.getLockScreenState === 'function') {
    const live = await MishilLockScreen.getLockScreenState();
    if (!live || !live.sleepActive) {
      await MishilLockScreen.startLiveSleep({
        startEpochMs: state.startEpochMs,
        sleepLabel: state.sleepLabel,
        subtitle: state.subtitle,
        babyName: state.babyName,
        showBabyNameOnLockScreen: state.showBabyNameOnLockScreen,
        lang: state.lang,
      });
    }
  }
}
