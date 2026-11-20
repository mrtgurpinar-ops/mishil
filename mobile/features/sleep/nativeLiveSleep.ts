import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import * as MishilLockScreen from '../../modules/mishil-lockscreen/src';

const STORAGE_KEY = '@mishil_live_sleep_native';
const MAX_SLEEP_AGE_MS = 16 * 3600000;
const MAX_NURSING_AGE_MS = 3 * 3600000;

export interface NativeLiveSleepState {
  active: boolean;
  startEpochMs: number;
  sleepLabel: string;
  subtitle: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
  lang: 'tr' | 'en' | 'de';
  mode?: 'sleep' | 'nursing';
  isPaused?: boolean;
  pausedElapsedSec?: number;
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
  mode?: 'sleep' | 'nursing';
  isPaused?: boolean;
  pausedElapsedSec?: number;
}): Promise<void> {
  if (!MishilLockScreen.isNativeLockScreenAvailable()) return;
  await maybeRequestNotificationPermission();

  const resolvedMode = options.mode === 'nursing' ? 'nursing' : 'sleep';
  const state: NativeLiveSleepState = {
    active: true,
    startEpochMs: options.startEpochMs,
    sleepLabel: options.sleepLabel,
    subtitle: options.subtitle || '',
    babyName: options.babyName,
    showBabyNameOnLockScreen: options.showBabyNameOnLockScreen,
    lang: options.lang || 'tr',
    mode: resolvedMode,
    isPaused: Boolean(options.isPaused),
    pausedElapsedSec: typeof options.pausedElapsedSec === 'number' ? Math.max(0, Math.floor(options.pausedElapsedSec)) : 0,
  };
  await writeState(state);
  await MishilLockScreen.startLiveSleep({
    startEpochMs: options.startEpochMs,
    sleepLabel: options.sleepLabel,
    subtitle: options.subtitle,
    babyName: options.babyName,
    showBabyNameOnLockScreen: options.showBabyNameOnLockScreen,
    lang: options.lang,
    mode: resolvedMode,
    isPaused: state.isPaused,
    pausedElapsedSec: state.pausedElapsedSec,
  });
}

export async function updateNativeLiveSleep(options: {
  startEpochMs: number;
  sleepLabel?: string;
  subtitle?: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
  mode?: 'sleep' | 'nursing';
  isPaused?: boolean;
  pausedElapsedSec?: number;
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
    mode: options.mode ? (options.mode === 'nursing' ? 'nursing' : 'sleep') : (current.mode || 'sleep'),
    isPaused: typeof options.isPaused === 'boolean' ? options.isPaused : current.isPaused,
    pausedElapsedSec: typeof options.pausedElapsedSec === 'number'
      ? Math.max(0, Math.floor(options.pausedElapsedSec))
      : current.pausedElapsedSec,
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
      mode: next.mode,
      isPaused: next.isPaused,
      pausedElapsedSec: next.pausedElapsedSec,
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
  const maxAgeMs = state.mode === 'nursing' ? MAX_NURSING_AGE_MS : MAX_SLEEP_AGE_MS;
  const age = state.isPaused && typeof state.pausedElapsedSec === 'number'
    ? state.pausedElapsedSec * 1000
    : Date.now() - state.startEpochMs;
  if (!state.startEpochMs || age > maxAgeMs) {
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
        mode: state.mode,
        isPaused: state.isPaused,
        pausedElapsedSec: state.pausedElapsedSec,
      });
    }
  }
}
