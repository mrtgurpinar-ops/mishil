import { requireOptionalNativeModule, type EventSubscription } from 'expo-modules-core';

export interface PlayAudioOptions {
  id: string;
  url: string;
  title: string;
  subtitle?: string;
  volume?: number;
  isVip: boolean;
  previewBudgetMs?: number;
}

export interface StartLiveSleepOptions {
  startEpochMs: number;
  sleepLabel: string;
  subtitle?: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
  lang?: 'tr' | 'en' | 'de';
}

export interface UpdateLiveSleepOptions {
  startEpochMs: number;
  sleepLabel?: string;
  subtitle?: string;
  babyName?: string;
  showBabyNameOnLockScreen?: boolean;
}

export interface LockScreenState {
  audioPlaying: boolean;
  audioPaused: boolean;
  audioId: string | null;
  previewElapsedMs: number;
  previewExhausted: boolean;
  sleepActive: boolean;
  sleepStartEpochMs: number | null;
}

export type PlaybackEventReason =
  | 'user'
  | 'track_switch'
  | 'remote_play'
  | 'remote_pause'
  | 'remote_stop'
  | 'preview_quota_exhausted'
  | 'error'
  | 'interrupted';

export interface PlaybackEvent {
  playing: boolean;
  paused?: boolean;
  id: string | null;
  reason: PlaybackEventReason;
  previewElapsedMs?: number;
}

interface MishilLockScreenNativeModule {
  playAudio(options: PlayAudioOptions): Promise<boolean>;
  pauseAudio(): Promise<void>;
  stopAudio(): Promise<void>;
  setAudioVolume(volume: number): Promise<void>;
  startLiveSleep(options: StartLiveSleepOptions): Promise<boolean>;
  updateLiveSleep(options: UpdateLiveSleepOptions): Promise<boolean>;
  stopLiveSleep(): Promise<void>;
  getLockScreenState(): Promise<LockScreenState>;
  addListener(eventName: 'onPlaybackStateChanged', listener: (event: PlaybackEvent) => void): EventSubscription;
}

const NativeModule = requireOptionalNativeModule<MishilLockScreenNativeModule>('MishilLockScreen');

const emptyState: LockScreenState = {
  audioPlaying: false,
  audioPaused: false,
  audioId: null,
  previewElapsedMs: 0,
  previewExhausted: false,
  sleepActive: false,
  sleepStartEpochMs: null,
};

export function isNativeLockScreenAvailable(): boolean {
  return NativeModule != null;
}

export async function playAudio(options: PlayAudioOptions): Promise<boolean> {
  if (!NativeModule) return false;
  try {
    return await NativeModule.playAudio(options);
  } catch {
    return false;
  }
}

export async function pauseAudio(): Promise<void> {
  if (!NativeModule) return;
  try {
    await NativeModule.pauseAudio();
  } catch {}
}

export async function stopAudio(): Promise<void> {
  if (!NativeModule) return;
  try {
    await NativeModule.stopAudio();
  } catch {}
}

export async function setAudioVolume(volume: number): Promise<void> {
  if (!NativeModule) return;
  try {
    await NativeModule.setAudioVolume(volume);
  } catch {}
}

export async function startLiveSleep(options: StartLiveSleepOptions): Promise<boolean> {
  if (!NativeModule) return false;
  try {
    return await NativeModule.startLiveSleep(options);
  } catch {
    return false;
  }
}

export async function updateLiveSleep(options: UpdateLiveSleepOptions): Promise<boolean> {
  if (!NativeModule) return false;
  try {
    return await NativeModule.updateLiveSleep(options);
  } catch {
    return false;
  }
}

export async function stopLiveSleep(): Promise<void> {
  if (!NativeModule) return;
  try {
    await NativeModule.stopLiveSleep();
  } catch {}
}

export async function getLockScreenState(): Promise<LockScreenState> {
  if (!NativeModule) return emptyState;
  try {
    return await NativeModule.getLockScreenState();
  } catch {
    return emptyState;
  }
}

export function addPlaybackListener(listener: (event: PlaybackEvent) => void): { remove: () => void } {
  if (!NativeModule || typeof NativeModule.addListener !== 'function') {
    return { remove: () => {} };
  }
  const sub = NativeModule.addListener('onPlaybackStateChanged', listener);
  return { remove: () => sub.remove() };
}
