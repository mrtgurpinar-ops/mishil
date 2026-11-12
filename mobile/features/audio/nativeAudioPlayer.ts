import { Audio, InterruptionModeIOS, InterruptionModeAndroid } from 'expo-av';
import * as MishilLockScreen from '../../modules/mishil-lockscreen/src';
import { storage } from '../../lib/storage';

/**
 * Native arka plan ses motoru.
 *
 * WKWebView / Android WebView içindeki <audio> ve Web Audio API ekran kilitlenince
 * durduğu için, ninni/gürültü çalma native tarafa taşındı. WebView yalnızca UI'dır;
 * `AUDIO_PLAY / AUDIO_STOP / AUDIO_TIMER / AUDIO_VOLUME` köprü mesajları buraya düşer.
 *
 * mishil-lockscreen yerel modülü derlenmişse (Build 69+ custom dev client / prod build)
 * ses + Now Playing + 60sn freemium kota MishilLockScreen üzerinden çalışır. Modül
 * henüz derlenmemiş eski kabuklarda veya Jest/Web ortamında expo-av akışına
 * kesintisiz fallback yapılır.
 */

export interface AudioState {
  playing: boolean;
  id: string | null;
  reason?: 'user' | 'timer' | 'track_switch' | 'error' | 'interrupted' | 'remote_play' | 'remote_pause' | 'remote_stop' | 'preview_quota_exhausted';
  previewElapsedMs?: number;
}

export interface PlaySoundMeta {
  title?: string;
  subtitle?: string;
  isVip?: boolean;
  previewBudgetMs?: number;
}

type StateListener = (s: AudioState) => void;

const useNativeLockScreen = MishilLockScreen.isNativeLockScreenAvailable();

let sound: Audio.Sound | null = null;
let currentId: string | null = null;
let userVolume = 1.0;
let currentVolume = 1.0;
let timer: ReturnType<typeof setTimeout> | null = null;
let fadeStartTimer: ReturnType<typeof setTimeout> | null = null;
let fadeInterval: ReturnType<typeof setInterval> | null = null;
let timerGen = 0;
let modeReady = false;

const FREE_PREVIEW_CAP_MS = 60000;
let activeStateListener: StateListener | null = null;
let nativeListenerSub: { remove: () => void } | null = null;
let inMemoryPreviewElapsedMs = 0;
let inMemoryPreviewExhausted = false;
let activeTrackBaseElapsedMs = 0;
let previousTrackBaseElapsedMs = 0;
let previousTrackWasVip = true;
let sessionIsVip = true;
const sessionBaseByTrack = new Map<string, number>();
let pendingQuotaWrite: Promise<unknown> = Promise.resolve();
let audioOpMutex: Promise<void> = Promise.resolve();
let audioOpGen = 0;

function enqueueAudioOp(fn: (opGen: number) => Promise<void>): Promise<void> {
  const opGen = ++audioOpGen;
  const next = audioOpMutex.then(
    () => fn(opGen),
    () => fn(opGen)
  );
  audioOpMutex = next.catch(() => {});
  return next;
}

function persistPreviewUsage(elapsedMs: number, forceExhausted = false): number {
  const clamped = Math.max(0, Math.min(FREE_PREVIEW_CAP_MS, Math.round(elapsedMs)));
  inMemoryPreviewElapsedMs = Math.max(inMemoryPreviewElapsedMs, clamped);
  const exhausted = forceExhausted || inMemoryPreviewExhausted || inMemoryPreviewElapsedMs >= FREE_PREVIEW_CAP_MS;
  if (exhausted) {
    inMemoryPreviewExhausted = true;
    inMemoryPreviewElapsedMs = FREE_PREVIEW_CAP_MS;
  }
  if (typeof storage.mergeDeviceQuotas === 'function') {
    const writePromise = Promise.resolve(
      storage.mergeDeviceQuotas({
        freeSoundUsed: exhausted,
        freeSoundElapsedMs: inMemoryPreviewElapsedMs,
      })
    ).catch(() => {});
    pendingQuotaWrite = Promise.all([pendingQuotaWrite, writePromise]).then(() => {});
  }
  return inMemoryPreviewElapsedMs;
}

function ensureNativeListener() {
  if (!useNativeLockScreen || nativeListenerSub) return;
  nativeListenerSub = MishilLockScreen.addPlaybackListener((event) => {
    if (event.reason === 'track_switch') {
      if (!previousTrackWasVip && typeof event.previewElapsedMs === 'number' && event.previewElapsedMs > 0) {
        const total = persistPreviewUsage(previousTrackBaseElapsedMs + event.previewElapsedMs);
        activeTrackBaseElapsedMs = Math.max(activeTrackBaseElapsedMs, total);
      }
      return;
    }

    let cumulativeElapsed: number | undefined;
    if (!sessionIsVip) {
      if (event.reason === 'preview_quota_exhausted') {
        cumulativeElapsed = persistPreviewUsage(FREE_PREVIEW_CAP_MS, true);
        activeTrackBaseElapsedMs = FREE_PREVIEW_CAP_MS;
      } else if (typeof event.previewElapsedMs === 'number' && event.previewElapsedMs > 0) {
        const eventBase =
          event.id && sessionBaseByTrack.has(event.id)
            ? sessionBaseByTrack.get(event.id)!
            : activeTrackBaseElapsedMs;
        cumulativeElapsed = persistPreviewUsage(eventBase + event.previewElapsedMs);
        if (!event.playing && !event.paused) {
          activeTrackBaseElapsedMs = Math.max(activeTrackBaseElapsedMs, cumulativeElapsed);
        }
      }
    }
    currentId = event.playing ? event.id : null;
    activeStateListener?.({
      playing: event.playing,
      id: event.playing ? event.id : null,
      reason: event.reason,
      ...(typeof cumulativeElapsed === 'number' ? { previewElapsedMs: cumulativeElapsed } : {}),
    });
  });
}

async function ensureAudioMode() {
  if (modeReady) return;
  await Audio.setAudioModeAsync({
    playsInSilentModeIOS: true,        // sessiz moddayken bile çal (ninni!)
    staysActiveInBackground: true,     // ekran kilitli / arka plan
    interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
    shouldDuckAndroid: false,
    playThroughEarpieceAndroid: false,
  });
  modeReady = true;
}

function clearFadeOnly() {
  if (fadeStartTimer) {
    clearTimeout(fadeStartTimer);
    fadeStartTimer = null;
  }
  if (fadeInterval) {
    clearInterval(fadeInterval);
    fadeInterval = null;
  }
  currentVolume = userVolume;
}

function clearTimer() {
  timerGen++;
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  clearFadeOnly();
}

async function unloadInternal(keepTimer = false) {
  if (keepTimer) {
    clearFadeOnly();
  } else {
    clearTimer();
  }
  const s = sound;
  sound = null;
  currentId = null;
  if (s) {
    try {
      await s.stopAsync();
    } catch {}
    try {
      await s.unloadAsync();
    } catch {}
  }
}

async function loadAndPlay(id: string, url: string): Promise<void> {
  await ensureAudioMode();
  await unloadInternal(true);
  const { sound: snd } = await Audio.Sound.createAsync(
    { uri: url },
    { shouldPlay: true, isLooping: true, volume: userVolume },
  );
  sound = snd;
  currentId = id;
}

export function playSound(id: string, url: string, onState: StateListener, meta?: PlaySoundMeta): Promise<void> {
  activeStateListener = onState;
  return enqueueAudioOp(async (opGen) => {
    // Kuyrukta arkadan daha yeni bir play/stop komutu geldiyse eski başlatmayı iptal et
    if (opGen !== audioOpGen) return;

    if (useNativeLockScreen) {
      ensureNativeListener();
      clearTimer();
      const hadActivePreviewTrack = currentId !== null && !sessionIsVip;
      previousTrackWasVip = sessionIsVip;
      previousTrackBaseElapsedMs = activeTrackBaseElapsedMs;

      if (hadActivePreviewTrack && typeof MishilLockScreen.getLockScreenState === 'function') {
        try {
          const live = await MishilLockScreen.getLockScreenState();
          if (live && (live.previewExhausted || (typeof live.previewElapsedMs === 'number' && live.previewElapsedMs > 0))) {
            persistPreviewUsage(activeTrackBaseElapsedMs + (live.previewElapsedMs || 0), Boolean(live.previewExhausted));
          }
        } catch {}
      }

      const isVip = meta?.isVip !== false;
      sessionIsVip = isVip;
      let effectiveBudgetMs = meta?.previewBudgetMs;
      if (!isVip) {
        await pendingQuotaWrite;
        let storageElapsed = 0;
        let storageUsed = false;
        if (typeof storage.getDeviceQuotas === 'function') {
          try {
            const quotas = await storage.getDeviceQuotas();
            storageElapsed = Math.max(0, Math.min(FREE_PREVIEW_CAP_MS, Math.round(quotas?.freeSoundElapsedMs || 0)));
            storageUsed = Boolean(quotas?.freeSoundUsed);
          } catch {}
        }
        const persistedElapsed = Math.max(inMemoryPreviewElapsedMs, storageElapsed);
        inMemoryPreviewElapsedMs = persistedElapsed;
        const persistedUsed = inMemoryPreviewExhausted || storageUsed || persistedElapsed >= FREE_PREVIEW_CAP_MS;
        const maxRemaining = Math.max(0, FREE_PREVIEW_CAP_MS - persistedElapsed);
        if (persistedUsed || maxRemaining <= 0) {
          if (hadActivePreviewTrack) {
            await MishilLockScreen.stopAudio();
          }
          currentId = null;
          persistPreviewUsage(FREE_PREVIEW_CAP_MS, true);
          if (opGen === audioOpGen) {
            onState({ playing: false, id: null, reason: 'preview_quota_exhausted', previewElapsedMs: FREE_PREVIEW_CAP_MS });
          }
          return;
        }
        activeTrackBaseElapsedMs = persistedElapsed;
        sessionBaseByTrack.set(id, persistedElapsed);
        effectiveBudgetMs =
          typeof meta?.previewBudgetMs === 'number' && meta.previewBudgetMs > 0
            ? Math.min(meta.previewBudgetMs, maxRemaining)
            : maxRemaining;
      } else {
        activeTrackBaseElapsedMs = 0;
        sessionBaseByTrack.delete(id);
      }

      if (opGen !== audioOpGen) return;

      const ok = await MishilLockScreen.playAudio({
        id,
        url,
        title: meta?.title || 'Mışıl Baby',
        subtitle: meta?.subtitle,
        volume: userVolume,
        isVip,
        previewBudgetMs: effectiveBudgetMs,
      });
      if (ok) {
        currentId = id;
        if (opGen === audioOpGen) {
          onState({ playing: true, id });
        }
        return;
      }
      // Native oynatma reddedildi (örn. kota bitmiş) — expo-av'a düşmeden hatayı bildir
      currentId = null;
      if (opGen === audioOpGen) {
        onState({
          playing: false,
          id: null,
          reason: !isVip && (effectiveBudgetMs ?? 0) <= 0 ? 'preview_quota_exhausted' : 'error',
        });
      }
      return;
    }

    // 1. deneme normal URL; hata olursa 2. deneme cache-bust ile (iOS AVPlayer kısmi/bozuk
    // cache'i bazen atlatır). İki deneme de olmazsa 'error'.
    for (let attempt = 0; attempt < 2; attempt++) {
      if (opGen !== audioOpGen) return;
      const tryUrl = attempt === 0 ? url : `${url}${url.includes('?') ? '&' : '?'}rc=${Date.now()}`;
      try {
        await loadAndPlay(id, tryUrl);
        sound?.setOnPlaybackStatusUpdate((st: any) => {
          if (!st) return;
          if (!st.isLoaded && st.error) {
            onState({ playing: false, id: null, reason: 'error' });
            void unloadInternal();
          }
        });
        onState({ playing: true, id });
        return;
      } catch (e) {
        console.log(`[nativeAudio] playSound deneme ${attempt + 1} hatası:`, e);
        await unloadInternal(attempt === 0);
      }
    }
    onState({ playing: false, id: null, reason: 'error' });
  });
}

export function stopSound(onState: StateListener, reason: AudioState['reason'] = 'user'): Promise<void> {
  activeStateListener = onState;
  clearTimer();
  return enqueueAudioOp(async (opGen) => {
    if (useNativeLockScreen) {
      const stoppingTrackId = currentId;
      const stoppingBase =
        stoppingTrackId && sessionBaseByTrack.has(stoppingTrackId)
          ? sessionBaseByTrack.get(stoppingTrackId)!
          : activeTrackBaseElapsedMs;
      if (stoppingTrackId !== null && !sessionIsVip && typeof MishilLockScreen.getLockScreenState === 'function') {
        try {
          const live = await MishilLockScreen.getLockScreenState();
          if (live && (live.previewExhausted || (typeof live.previewElapsedMs === 'number' && live.previewElapsedMs > 0))) {
            persistPreviewUsage(
              stoppingBase + (live.previewElapsedMs || 0),
              Boolean(live.previewExhausted)
            );
          }
        } catch {}
      }
      await MishilLockScreen.stopAudio();
      activeTrackBaseElapsedMs = Math.max(activeTrackBaseElapsedMs, inMemoryPreviewElapsedMs);
      await pendingQuotaWrite;
      currentId = null;
      if (opGen === audioOpGen) {
        onState({ playing: false, id: null, reason });
      }
      return;
    }
    await unloadInternal();
    if (opGen === audioOpGen) {
      onState({ playing: false, id: null, reason });
    }
  });
}

export async function setVolume(value: number, isFadeStep = false): Promise<void> {
  currentVolume = Math.max(0, Math.min(1, value));
  if (!isFadeStep && currentVolume > 0.05) {
    userVolume = currentVolume;
  }
  if (useNativeLockScreen) {
    await MishilLockScreen.setAudioVolume(currentVolume);
    return;
  }
  if (sound) {
    try {
      await sound.setStatusAsync({ volume: currentVolume });
    } catch {}
  }
}

/** minutes <= 0 => zamanlayıcı iptal (sürekli çal) */
export function startTimer(minutes: number, onState: StateListener, fadeOut = true): void {
  activeStateListener = onState;
  clearTimer();
  if (!minutes || minutes <= 0) return;

  const gen = timerGen;
  const totalMs = Math.max(1000, Math.round(minutes * 60000));
  const baseVol = userVolume > 0.05 ? userVolume : 1.0;

  const hasActiveTarget = () => (useNativeLockScreen ? !!currentId : !!sound);

  if (fadeOut) {
    const fadeDurationMs = Math.min(30000, Math.floor(totalMs * 0.5));
    const fadeStartDelayMs = Math.max(0, totalMs - fadeDurationMs);
    fadeStartTimer = setTimeout(() => {
      if (gen !== timerGen) return;
      const steps = 20;
      const stepMs = Math.max(250, Math.floor(fadeDurationMs / steps));
      let step = 0;
      fadeInterval = setInterval(() => {
        if (gen !== timerGen || !hasActiveTarget()) {
          clearFadeOnly();
          return;
        }
        step++;
        const nextVol = Math.max(0.03, Number((baseVol * (1 - step / steps)).toFixed(2)));
        void setVolume(nextVol, true);
        if (step >= steps && fadeInterval) {
          clearInterval(fadeInterval);
          fadeInterval = null;
        }
      }, stepMs);
    }, fadeStartDelayMs);
  }

  timer = setTimeout(() => {
    if (gen !== timerGen) return;
    if (hasActiveTarget()) {
      void stopSound(onState, 'timer');
    } else {
      clearTimer();
    }
  }, totalMs);
}

export function getCurrentId(): string | null {
  return currentId;
}

export function shutdown(): Promise<void> {
  clearTimer();
  return enqueueAudioOp(async () => {
    if (useNativeLockScreen) {
      await MishilLockScreen.stopAudio();
      nativeListenerSub?.remove();
      nativeListenerSub = null;
      currentId = null;
      return;
    }
    await unloadInternal();
  });
}
